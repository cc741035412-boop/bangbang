import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import main
from models import (
    Account,
    Area,
    AuthSession,
    Child,
    ClassRoom,
    Media,
    Observation,
    ObservationChild,
    ObservationTag,
    SMSCode,
)
from time_utils import utc_now


class AuthFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)
        main.engine = self.engine
        main.UPLOAD_DIR = Path(self.temp_dir.name) / "uploads"
        main.UPLOAD_DIR.mkdir()
        self.patchers = [
            patch.object(main, "SMS_PROVIDER", "mock"),
            patch.object(main, "SMS_MOCK_CODE", "123456"),
            patch.object(main, "RUNTIME_ENV", "development"),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def register(self, phone="13800000001"):
        sent = self.client.post("/auth/code", json={"phone": phone})
        self.assertEqual(sent.status_code, 200, sent.text)
        response = self.client.post(
            "/auth/register",
            json={
                "phone": phone,
                "code": "123456",
                "name": "教师A",
                "kindergarten_name": "测试幼儿园A",
                "classroom_name": "中一班",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def bearer(token):
        return {"Authorization": f"Bearer {token}"}

    def test_register_me_logout_and_observation_ownership(self):
        registered = self.register()
        token = registered["access_token"]
        account = registered["account"]
        self.assertEqual(registered["expires_in"], 2592000)
        self.assertEqual(account["name"], "教师A")
        self.assertEqual(account["kindergarten_name"], "测试幼儿园A")
        self.assertEqual(account["classroom_name"], "中一班")

        me = self.client.get("/auth/me", headers=self.bearer(token))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json(), account)

        with Session(self.engine) as session:
            area = Area(code="construction", name="建构区")
            session.add(area)
            session.commit()
            session.refresh(area)
            area_id = area.id
        observation = self.client.post(
            "/observations",
            headers=self.bearer(token),
            json={"area_id": area_id, "note": "虚构观察记录"},
        )
        self.assertEqual(observation.status_code, 201, observation.text)
        self.assertEqual(observation.json()["observer_id"], account["teacher_id"])
        self.assertEqual(observation.json()["classroom_id"], account["classroom_id"])

        logged_out = self.client.post("/auth/logout", headers=self.bearer(token))
        self.assertEqual(logged_out.status_code, 204)
        self.assertEqual(
            self.client.get("/auth/me", headers=self.bearer(token)).status_code,
            401,
        )

    def test_child_profile_uses_confirmed_facts_and_only_safe_dimensions(self):
        registered = self.register("13800000009")
        token = registered["access_token"]
        classroom_id = registered["account"]["classroom_id"]
        now = utc_now()
        with Session(self.engine) as session:
            area = Area(code="construction", name="建构区")
            child = Child(name="幼儿A", classroom_id=classroom_id, gender="女")
            session.add(area)
            session.add(child)
            session.flush()
            confirmed = Observation(
                child_id=child.id,
                area_id=area.id,
                classroom_id=classroom_id,
                age_group="middle",
                status="confirmed",
                observed_at=now,
            )
            draft = Observation(
                child_id=child.id,
                area_id=area.id,
                classroom_id=classroom_id,
                age_group="middle",
                status="uploaded",
                observed_at=now - timedelta(days=1),
            )
            session.add(confirmed)
            session.add(draft)
            session.flush()
            session.add(ObservationChild(
                observation_id=confirmed.id,
                child_id=child.id,
                is_primary=True,
            ))
            session.add(Media(
                stored_filename="fictitious.jpg",
                content_type="image/jpeg",
                size=10,
                observation_id=draft.id,
                uploaded_at=now - timedelta(days=1),
            ))
            session.add(ObservationTag(
                observation_id=confirmed.id,
                indicator_code="1.1",
                indicator_name="身体行为参与度",
                level=1,
                source="teacher_added",
                accepted=True,
            ))
            session.add(ObservationTag(
                observation_id=confirmed.id,
                indicator_code="1.2",
                indicator_name="身体探索方式",
                level=1,
                source="teacher_added",
                accepted=True,
            ))
            session.add(ObservationTag(
                observation_id=confirmed.id,
                indicator_code="4.1",
                indicator_name="认知指标",
                level=1,
                source="teacher_added",
                accepted=True,
            ))
            other_room = ClassRoom(name="大一班", age_group="large")
            session.add(other_room)
            session.flush()
            other_child = Child(name="幼儿B", classroom_id=other_room.id)
            session.add(other_child)
            session.commit()
            child_id = child.id
            other_child_id = other_child.id

        response = self.client.get(
            f"/children/{child_id}/profile",
            headers=self.bearer(token),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["name"], "幼儿A")
        self.assertEqual(body["gender"], "female")
        self.assertEqual(body["media_count"], 1)
        self.assertEqual(body["record_count"], 1)
        self.assertEqual(body["observed_day_count"], 2)
        self.assertEqual(body["dimension_counts"], {"身体参与": 1, "社会互动": 0})
        self.assertEqual(len(body["records"]), 1)
        self.assertEqual(body["records"][0]["title"], "建构区观察记录")
        self.assertEqual(body["records"][0]["dimensions"], ["身体参与"])
        self.assertFalse(body["records"][0]["exported"])
        self.assertNotIn("score", body)
        self.assertEqual(
            TestClient(main.app).get(f"/children/{child_id}/profile").status_code,
            401,
        )
        self.assertEqual(
            self.client.get(
                f"/children/{other_child_id}/profile",
                headers=self.bearer(token),
            ).status_code,
            404,
        )

    def test_create_and_guarded_delete_child(self):
        registered = self.register("13800000008")
        headers = self.bearer(registered["access_token"])
        created = self.client.post(
            "/children",
            headers=headers,
            json={
                "name": "幼儿A",
                "birth_date": "2021-05-06",
                "gender": "female",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        child_id = created.json()["id"]
        with Session(self.engine) as session:
            child = session.get(Child, child_id)
            self.assertEqual(child.name, "幼儿A")
            self.assertEqual(child.classroom_id, registered["account"]["classroom_id"])
            self.assertEqual(getattr(child.gender, "value", child.gender), "女")
            area = Area(code="art", name="美工区")
            session.add(area)
            session.flush()
            observation = Observation(
                child_id=child.id,
                area_id=area.id,
                classroom_id=child.classroom_id,
                age_group="middle",
            )
            session.add(observation)
            session.flush()
            session.add(Media(
                stored_filename="fictitious.png",
                content_type="image/png",
                size=8,
                observation_id=observation.id,
            ))
            session.commit()

        guarded = self.client.delete(f"/children/{child_id}", headers=headers)
        self.assertEqual(guarded.status_code, 409, guarded.text)
        self.assertEqual(
            guarded.json()["detail"],
            "幼儿A名下还有 1 条素材、1 篇记录，请先处理后再删除",
        )
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(Child, child_id))

        empty = self.client.post(
            "/children",
            headers=headers,
            json={"name": "幼儿B"},
        )
        self.assertEqual(empty.status_code, 201, empty.text)
        deleted = self.client.delete(
            f"/children/{empty.json()['id']}",
            headers=headers,
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)
        with Session(self.engine) as session:
            self.assertIsNone(session.get(Child, empty.json()["id"]))

    def test_multi_child_association_replaces_all_and_syncs_primary(self):
        registered = self.register("13800000007")
        headers = self.bearer(registered["access_token"])
        classroom_id = registered["account"]["classroom_id"]
        with Session(self.engine) as session:
            area = Area(code="sand", name="沙水区")
            child_a = Child(name="幼儿A", classroom_id=classroom_id)
            child_b = Child(name="幼儿B", classroom_id=classroom_id)
            other_room = ClassRoom(name="大二班", age_group="large")
            session.add(area)
            session.add(child_a)
            session.add(child_b)
            session.add(other_room)
            session.flush()
            other_child = Child(name="幼儿C", classroom_id=other_room.id)
            session.add(other_child)
            session.commit()
            area_id = area.id
            child_a_id = child_a.id
            child_b_id = child_b.id
            other_child_id = other_child.id

        created = self.client.post(
            "/observations",
            headers=headers,
            json={"area_id": area_id, "child_id": child_a_id},
        )
        self.assertEqual(created.status_code, 201, created.text)
        observation_id = created.json()["id"]
        associated = self.client.put(
            f"/observations/{observation_id}/children",
            headers=headers,
            json={"child_ids": [child_b_id, child_a_id, child_b_id]},
        )
        self.assertEqual(associated.status_code, 200, associated.text)
        self.assertEqual(associated.json(), {"child_ids": [child_b_id, child_a_id]})
        with Session(self.engine) as session:
            observation = session.get(Observation, observation_id)
            self.assertEqual(observation.child_id, child_b_id)
            links = session.exec(
                select(ObservationChild)
                .where(ObservationChild.observation_id == observation_id)
                .order_by(ObservationChild.child_id)
            ).all()
            self.assertEqual({item.child_id for item in links}, {child_a_id, child_b_id})
            self.assertEqual(
                [item.child_id for item in links if item.is_primary],
                [child_b_id],
            )

        wrong_class = self.client.put(
            f"/observations/{observation_id}/children",
            headers=headers,
            json={"child_ids": [child_a_id, other_child_id]},
        )
        self.assertEqual(wrong_class.status_code, 422, wrong_class.text)
        empty = self.client.put(
            f"/observations/{observation_id}/children",
            headers=headers,
            json={"child_ids": []},
        )
        self.assertEqual(empty.status_code, 422, empty.text)

    def test_kindergarten_and_classroom_owner_management(self):
        registered = self.register("13800000005")
        headers = self.bearer(registered["access_token"])
        current = self.client.get("/kindergartens/current", headers=headers)
        self.assertEqual(current.status_code, 200, current.text)
        body = current.json()
        self.assertEqual(body["name"], "测试幼儿园A")
        self.assertEqual(body["my_role"], "owner")
        self.assertEqual(len(body["classrooms"]), 1)
        self.assertEqual(body["classrooms"][0]["name"], "中一班")
        self.assertEqual(body["teachers"][0]["phone"], "138****0005")

        renamed = self.client.patch(
            "/kindergartens/current",
            headers=headers,
            json={"name": "测试幼儿园B"},
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["name"], "测试幼儿园B")

        created = self.client.post(
            "/classrooms",
            headers=headers,
            json={"name": "小二班"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        classroom_id = created.json()["id"]
        self.assertEqual(created.json()["child_count"], 0)
        renamed_room = self.client.patch(
            f"/classrooms/{classroom_id}",
            headers=headers,
            json={"name": "大二班"},
        )
        self.assertEqual(renamed_room.status_code, 200, renamed_room.text)
        with Session(self.engine) as session:
            room = session.get(ClassRoom, classroom_id)
            self.assertEqual(room.age_group, "large")
            session.add(Child(name="幼儿A", classroom_id=room.id))
            session.commit()
        blocked = self.client.delete(f"/classrooms/{classroom_id}", headers=headers)
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertIn("还有 1 名幼儿", blocked.json()["detail"])

        with Session(self.engine) as session:
            account = session.exec(
                select(Account).where(Account.phone == "13800000005")
            ).one()
            account.role = "teacher"
            session.add(account)
            session.commit()
        forbidden = self.client.post(
            "/classrooms",
            headers=headers,
            json={"name": "托一班"},
        )
        self.assertEqual(forbidden.status_code, 403, forbidden.text)

    def test_successful_export_is_recorded_for_current_account(self):
        registered = self.register("13800000004")
        headers = self.bearer(registered["access_token"])
        classroom_id = registered["account"]["classroom_id"]
        teacher_id = registered["account"]["teacher_id"]
        with Session(self.engine) as session:
            area = Area(code="blocks", name="建构区")
            child = Child(name="幼儿A", classroom_id=classroom_id)
            session.add(area)
            session.add(child)
            session.flush()
            observation = Observation(
                child_id=child.id,
                area_id=area.id,
                classroom_id=classroom_id,
                observer_id=teacher_id,
                age_group="middle",
                status="confirmed",
                narrative="幼儿A将积木放在底板上。",
            )
            session.add(observation)
            session.flush()
            session.add(ObservationChild(
                observation_id=observation.id,
                child_id=child.id,
                is_primary=True,
            ))
            session.commit()
            observation_id = observation.id
            child_id = child.id

        exported = self.client.get(
            f"/observations/{observation_id}/export",
            headers=headers,
            params={"format": "md", "include_indicators": "true"},
        )
        self.assertEqual(exported.status_code, 200, exported.text)
        history = self.client.get("/exports/history", headers=headers)
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(len(history.json()), 1)
        record = history.json()[0]
        self.assertEqual(record["observation_id"], observation_id)
        self.assertEqual(record["scope"], "single")
        self.assertEqual(record["format"], "md")
        self.assertEqual(record["child_name"], "幼儿A")
        self.assertGreater(record["size"], 0)
        self.assertIsNone(record["download_url"])

        profile = self.client.get(
            f"/children/{child_id}/profile",
            headers=headers,
        )
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertTrue(profile.json()["records"][0]["exported"])

    def test_code_cooldown_expiry_and_one_time_consumption(self):
        phone = "13800000002"
        first = self.client.post("/auth/code", json={"phone": phone})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), {"expires_in": 300, "cooldown_sec": 60})
        limited = self.client.post("/auth/code", json={"phone": phone})
        self.assertEqual(limited.status_code, 429)

        with Session(self.engine) as session:
            sms = session.exec(select(SMSCode).where(SMSCode.phone == phone)).one()
            sms.expires_at = utc_now() - timedelta(seconds=1)
            session.add(sms)
            session.commit()
        expired = self.client.post(
            "/auth/register",
            json={
                "phone": phone,
                "code": "123456",
                "name": "教师B",
                "kindergarten_name": "测试幼儿园B",
                "classroom_name": "小一班",
            },
        )
        self.assertEqual(expired.status_code, 400)

        with Session(self.engine) as session:
            sms = session.exec(select(SMSCode).where(SMSCode.phone == phone)).one()
            sms.expires_at = utc_now() + timedelta(minutes=5)
            session.add(sms)
            session.commit()
        registered = self.client.post(
            "/auth/register",
            json={
                "phone": phone,
                "code": "123456",
                "name": "教师B",
                "kindergarten_name": "测试幼儿园B",
                "classroom_name": "小一班",
            },
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        with Session(self.engine) as session:
            sms = session.exec(select(SMSCode).where(SMSCode.phone == phone)).one()
            self.assertIsNotNone(sms.consumed_at)

        anonymous = TestClient(main.app)
        with patch.object(main, "SMS_COOLDOWN_SECONDS", 0):
            sent_login = anonymous.post("/auth/code", json={"phone": phone})
        self.assertEqual(sent_login.status_code, 200)
        login_body = {"phone": phone, "code": "123456"}
        self.assertEqual(anonymous.post("/auth/login", json=login_body).status_code, 200)
        self.assertEqual(anonymous.post("/auth/login", json=login_body).status_code, 400)

    def test_stale_token_does_not_block_login_or_registration_code(self):
        stale_headers = {"Authorization": "Bearer expired-or-unknown-token"}
        response = self.client.post(
            "/auth/code",
            headers=stale_headers,
            json={"phone": "13800000006"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"expires_in": 300, "cooldown_sec": 60})
        with Session(self.engine) as session:
            code = session.exec(
                select(SMSCode).where(SMSCode.phone == "13800000006")
            ).one()
            self.assertEqual(code.purpose, "register")

    def test_login_change_phone_and_delete_account(self):
        old_phone = "13800000003"
        new_phone = "13800000004"
        registered = self.register(old_phone)
        token = registered["access_token"]
        headers = self.bearer(token)

        with patch.object(main, "SMS_COOLDOWN_SECONDS", 0):
            self.assertEqual(
                self.client.post("/auth/code", headers=headers, json={"phone": new_phone}).status_code,
                200,
            )
        changed = self.client.patch(
            "/auth/phone",
            headers=headers,
            json={"new_phone": new_phone, "code": "123456"},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["phone"], new_phone)

        with Session(self.engine) as session:
            area = Area(code="role", name="角色区")
            session.add(area)
            session.commit()
            session.refresh(area)
            area_id = area.id
        uploaded = self.client.post(
            "/uploads",
            files={"file": ("mock.jpg", b"mock-image", "image/jpeg")},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        media_id = uploaded.json()["id"]
        stored_name = uploaded.json()["stored_filename"]
        observation = self.client.post(
            "/observations",
            headers=headers,
            json={"area_id": area_id},
        )
        self.assertEqual(observation.status_code, 201, observation.text)
        observation_id = observation.json()["id"]
        attached = self.client.post(
            f"/observations/{observation_id}/attach-media?media_id={media_id}"
        )
        self.assertEqual(attached.status_code, 200, attached.text)
        self.assertTrue((main.UPLOAD_DIR / stored_name).exists())

        with patch.object(main, "SMS_COOLDOWN_SECONDS", 0):
            self.assertEqual(
                self.client.post("/auth/code", headers=headers, json={"phone": new_phone}).status_code,
                200,
            )
        deleted = self.client.request(
            "DELETE",
            "/auth/account",
            headers=headers,
            json={"code": "123456"},
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 401)

        with Session(self.engine) as session:
            account = session.exec(select(Account).where(Account.phone == new_phone)).one()
            self.assertIsNotNone(account.deleted_at)
            sessions = session.exec(
                select(AuthSession).where(AuthSession.account_id == account.id)
            ).all()
            self.assertTrue(sessions)
            self.assertTrue(all(item.revoked_at is not None for item in sessions))
            self.assertIsNone(session.get(Observation, observation_id))
            self.assertIsNone(session.get(Media, media_id))
        self.assertFalse((main.UPLOAD_DIR / stored_name).exists())

    def test_provider_never_falls_back_to_mock_in_production(self):
        with patch.object(main, "RUNTIME_ENV", "production"):
            response = self.client.post("/auth/code", json={"phone": "13800000005"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("生产环境", response.json()["detail"])

        with patch.object(main, "SMS_PROVIDER", ""):
            response = self.client.post("/auth/code", json={"phone": "13800000006"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("短信服务尚未配置", response.json()["detail"])

    def test_login_requires_existing_account(self):
        response = self.client.post(
            "/auth/login",
            json={"phone": "13800000007", "code": "123456"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("还没有注册", response.json()["detail"])

        validation = self.client.post("/auth/login", json={"phone": "13800000007"})
        self.assertEqual(validation.status_code, 422)
        self.assertIsInstance(validation.json()["detail"], str)
        self.assertIn("填写信息", validation.json()["detail"])


if __name__ == "__main__":
    unittest.main()
