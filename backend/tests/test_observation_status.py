import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import main
from models import Area, Child, ClassRoom, Observation


class ObservationStatusFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        main.engine = engine
        main.UPLOAD_DIR = Path(self.temp_dir.name) / "uploads"
        main.UPLOAD_DIR.mkdir()
        self.client = TestClient(main.app)

        with Session(engine) as session:
            area = Area(code="construction", name="建构区")
            room = ClassRoom(name="中二班", age_group="middle")
            session.add(area)
            session.add(room)
            session.commit()
            session.refresh(area)
            session.refresh(room)
            child = Child(name="测试幼儿A", classroom_id=room.id)
            session.add(child)
            session.commit()
            session.refresh(child)
            self.area_id = area.id
            self.child_id = child.id

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_bound_observation(self):
        media_response = self.client.post(
            "/uploads?duration_sec=2100",
            files={"file": ("mock.mp4", b"mock-video", "video/mp4")},
        )
        self.assertEqual(media_response.status_code, 201)
        media_id = media_response.json()["id"]

        rejected_status = self.client.post(
            "/observations",
            json={
                "area_id": self.area_id,
                "status": "confirmed",
            },
        )
        self.assertEqual(rejected_status.status_code, 422)

        create_response = self.client.post(
            "/observations",
            json={
                "child_id": self.child_id,
                "area_id": self.area_id,
                "note": "测试状态流转",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        observation = create_response.json()
        self.assertEqual(observation["status"], "uploaded")

        attach_response = self.client.post(
            f"/observations/{observation['id']}/attach-media?media_id={media_id}"
        )
        self.assertEqual(attach_response.status_code, 200)
        self.assertEqual(attach_response.json()["status"], "uploaded")
        return observation["id"]

    def test_complete_flow_filter_and_illegal_transition(self):
        observation_id = self.create_bound_observation()

        illegal = self.client.post(f"/observations/{observation_id}/confirm")
        self.assertEqual(illegal.status_code, 400)
        self.assertEqual(illegal.json()["detail"]["current_status"], "uploaded")
        self.assertEqual(illegal.json()["detail"]["target_status"], "confirmed")

        narrative = self.client.post(f"/observations/{observation_id}/narrative")
        self.assertEqual(narrative.status_code, 200)
        self.assertEqual(narrative.json()["status"], "processing")
        self.assertIsNotNone(narrative.json()["processing_started_at"])

        suggestions = self.client.post(f"/observations/{observation_id}/suggest-tags")
        self.assertEqual(suggestions.status_code, 200)
        self.assertEqual(suggestions.json()["status"], "ready_for_review")
        self.assertIsNotNone(suggestions.json()["ready_at"])
        self.assertTrue(suggestions.json()["suggestions"])

        update_context = self.client.patch(
            f"/observations/{observation_id}",
            json={"child_id": self.child_id, "note": "确认时补充"},
        )
        self.assertEqual(update_context.status_code, 200)
        self.assertEqual(update_context.json()["note"], "确认时补充")

        ready_items = self.client.get(
            "/observations", params={"status": "ready_for_review"}
        )
        self.assertEqual(ready_items.status_code, 200)
        self.assertEqual([item["id"] for item in ready_items.json()], [observation_id])

        first_tag_id = suggestions.json()["suggestions"][0]["tag_id"]
        decision = self.client.patch(
            f"/observations/{observation_id}/tags/{first_tag_id}",
            json={"accepted": True},
        )
        self.assertEqual(decision.status_code, 200)

        confirmed = self.client.post(f"/observations/{observation_id}/confirm")
        self.assertEqual(confirmed.status_code, 200)
        confirmed_observation = confirmed.json()["observation"]
        self.assertEqual(confirmed_observation["status"], "confirmed")
        self.assertIsNotNone(confirmed_observation["confirmed_at"])

    def test_ai_failure_and_retry(self):
        observation_id = self.create_bound_observation()

        with patch.object(
            main.ai_service,
            "generate_narrative",
            side_effect=RuntimeError("mock workflow unavailable"),
        ):
            failed = self.client.post(f"/observations/{observation_id}/narrative")

        self.assertEqual(failed.status_code, 500)
        with Session(main.engine) as session:
            observation = session.get(Observation, observation_id)
            self.assertEqual(observation.status, "failed")
            self.assertIn("mock workflow unavailable", observation.failure_reason)

        retried = self.client.post(f"/observations/{observation_id}/narrative")
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()["status"], "processing")

    def test_quick_capture_defaults_media_inference_and_child_update(self):
        created = self.client.post("/observations", json={"area_id": self.area_id})
        self.assertEqual(created.status_code, 201)
        observation = created.json()
        self.assertEqual(observation["status"], "uploaded")
        self.assertIsNone(observation["child_id"])
        self.assertEqual(observation["classroom_id"], 1)
        self.assertEqual(observation["age_group"], "middle")
        self.assertIsNone(observation["media_type"])

        missing_area = self.client.post("/observations", json={})
        self.assertEqual(missing_area.status_code, 422)

        jpg = self.client.post(
            "/uploads",
            files={"file": ("mock.jpg", b"mock-image", "image/jpeg")},
        )
        self.assertEqual(jpg.status_code, 201)
        attached_jpg = self.client.post(
            f"/observations/{observation['id']}/attach-media",
            params={"media_id": jpg.json()["id"]},
        )
        self.assertEqual(attached_jpg.status_code, 200)
        self.assertEqual(attached_jpg.json()["media_type"], "image")

        second_media = self.client.post(
            "/uploads",
            files={"file": ("second.mp4", b"second-video", "video/mp4")},
        )
        attached_second = self.client.post(
            f"/observations/{observation['id']}/attach-media",
            params={"media_id": second_media.json()["id"]},
        )
        self.assertEqual(attached_second.status_code, 200)
        self.assertEqual(attached_second.json()["media_type"], "image")

        video_observation = self.client.post(
            "/observations", json={"area_id": self.area_id}
        ).json()
        mp4 = self.client.post(
            "/uploads",
            files={"file": ("mock.mp4", b"mock-video", "video/mp4")},
        )
        self.assertEqual(mp4.status_code, 201)
        attached_mp4 = self.client.post(
            f"/observations/{video_observation['id']}/attach-media",
            params={"media_id": mp4.json()["id"]},
        )
        self.assertEqual(attached_mp4.status_code, 200)
        self.assertEqual(attached_mp4.json()["media_type"], "video")

        original_classroom_id = observation["classroom_id"]
        original_age_group = observation["age_group"]
        updated = self.client.patch(
            f"/observations/{observation['id']}",
            json={"child_id": self.child_id, "note": "回看时确认幼儿"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["child_id"], self.child_id)
        self.assertEqual(updated.json()["note"], "回看时确认幼儿")
        self.assertEqual(updated.json()["classroom_id"], original_classroom_id)
        self.assertEqual(updated.json()["age_group"], original_age_group)

    def test_upload_limit_and_read_media_file(self):
        image_content = b"mock-image-content"
        uploaded = self.client.post(
            "/uploads",
            files={"file": ("mock.jpg", image_content, "image/jpeg")},
        )
        self.assertEqual(uploaded.status_code, 201)

        media_file = self.client.get(f"/media/{uploaded.json()['id']}/file")
        self.assertEqual(media_file.status_code, 200)
        self.assertEqual(media_file.headers["content-type"], "image/jpeg")
        self.assertEqual(media_file.content, image_content)

        missing = self.client.get("/media/999999/file")
        self.assertEqual(missing.status_code, 404)

        with patch.object(main, "MAX_SIZE", 8):
            too_large = self.client.post(
                "/uploads",
                files={"file": ("large.mp4", b"123456789", "video/mp4")},
            )
        self.assertEqual(too_large.status_code, 413)
        self.assertEqual(too_large.json()["detail"], "文件不能超过 200MB")

    def test_iphone_media_types_and_extension_fallback(self):
        cases = [
            ("iphone.mov", "video/quicktime", "video/quicktime", "video"),
            ("iphone.heic", "image/heic", "image/heic", "image"),
            ("iphone.heif", "image/heif", "image/heif", "image"),
            ("fallback.mov", "application/octet-stream", "video/quicktime", "video"),
            ("fallback.heic", "", "image/heic", "image"),
            ("fallback.heif", "application/octet-stream", "image/heif", "image"),
            ("fallback.jpg", "application/octet-stream", "image/jpeg", "image"),
            ("fallback.jpeg", "application/octet-stream", "image/jpeg", "image"),
            ("fallback.png", "application/octet-stream", "image/png", "image"),
            ("fallback.mp4", "application/octet-stream", "video/mp4", "video"),
        ]

        for filename, sent_type, expected_type, expected_media_type in cases:
            with self.subTest(filename=filename, sent_type=sent_type):
                uploaded = self.client.post(
                    "/uploads",
                    files={"file": (filename, b"mock-iphone-media", sent_type)},
                )
                self.assertEqual(uploaded.status_code, 201)
                self.assertEqual(uploaded.json()["content_type"], expected_type)

                observation = self.client.post(
                    "/observations", json={"area_id": self.area_id}
                ).json()
                attached = self.client.post(
                    f"/observations/{observation['id']}/attach-media",
                    params={"media_id": uploaded.json()["id"]},
                )
                self.assertEqual(attached.status_code, 200)
                self.assertEqual(attached.json()["media_type"], expected_media_type)

        rejected = self.client.post(
            "/uploads",
            files={"file": ("notes.txt", b"not-media", "text/plain")},
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(
            rejected.json()["detail"],
            "只支持照片和视频（JPG、PNG、HEIC、MP4、MOV）",
        )

    def test_utc_timestamps_and_legacy_local_time_response(self):
        created = self.client.post("/observations", json={"area_id": self.area_id})
        self.assertEqual(created.status_code, 201)
        created_at = created.json()["created_at"]
        self.assertTrue(created_at.endswith("Z") or created_at.endswith("+00:00"))

        with main.engine.begin() as connection:
            stored = connection.execute(
                text("SELECT created_at FROM observation WHERE id = :id"),
                {"id": created.json()["id"]},
            ).scalar_one()
            self.assertTrue(stored.endswith("Z") or stored.endswith("+00:00"))
            connection.execute(
                text("UPDATE observation SET created_at = :created_at WHERE id = :id"),
                {
                    "id": created.json()["id"],
                    "created_at": "2026-08-23 05:34:32.426166",
                },
            )

        legacy = self.client.get(f"/observations/{created.json()['id']}")
        self.assertEqual(legacy.status_code, 200)
        expected = datetime(2026, 8, 23, 12, 34, 32, 426166, tzinfo=timezone.utc)
        actual = datetime.fromisoformat(legacy.json()["created_at"].replace("Z", "+00:00"))
        self.assertEqual(actual, expected)

    def test_video_thumbnail_success_and_failure_reason(self):
        def create_thumbnail(source_path):
            main.get_thumbnail_path(source_path.name).write_bytes(b"mock-png")
            return None

        with patch.object(main, "generate_video_thumbnail", side_effect=create_thumbnail):
            uploaded = self.client.post(
                "/uploads",
                files={"file": ("iphone.mov", b"mock-mov", "video/quicktime")},
            )

        self.assertEqual(uploaded.status_code, 201)
        thumbnail = self.client.get(f"/media/{uploaded.json()['id']}/thumbnail")
        self.assertEqual(thumbnail.status_code, 200)
        self.assertEqual(thumbnail.headers["content-type"], "image/png")
        self.assertEqual(thumbnail.content, b"mock-png")

        def fail_thumbnail(source_path):
            reason = "当前视频编码暂时无法生成缩略图"
            main.get_thumbnail_error_path(source_path.name).write_text(reason, encoding="utf-8")
            return reason

        with patch.object(main, "generate_video_thumbnail", side_effect=fail_thumbnail):
            failed_upload = self.client.post(
                "/uploads",
                files={"file": ("unsupported.mov", b"bad-codec", "video/quicktime")},
            )
        failed_media = failed_upload.json()
        self.assertIsNotNone(failed_media["thumbnail_failure_reason"])
        failed_thumbnail = self.client.get(f"/media/{failed_media['id']}/thumbnail")
        self.assertEqual(failed_thumbnail.status_code, 404)
        self.assertEqual(
            failed_thumbnail.json()["detail"]["reason"],
            failed_media["thumbnail_failure_reason"],
        )

        with patch.object(main, "generate_video_thumbnail", side_effect=create_thumbnail):
            retried_thumbnail = self.client.get(f"/media/{failed_media['id']}/thumbnail")
        self.assertEqual(retried_thumbnail.status_code, 200)
        refreshed_media = self.client.get("/media").json()
        retried_media = next(item for item in refreshed_media if item["id"] == failed_media["id"])
        self.assertIsNone(retried_media["thumbnail_failure_reason"])


if __name__ == "__main__":
    unittest.main()
