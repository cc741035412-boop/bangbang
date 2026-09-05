"""GET /observations 按幼儿 / 区域 / 观察日期区间检索的回归测试。

只使用内存临时库（create_all + main.engine 替换），绝不触碰真实 bangbang.db。
日期语义与观察文书一致：date_from / date_to 是 Asia/Shanghai 自然日，含当天；
UTC 16:30 落在北京时间次日 00:30，用于验证“当地零点”换算没有按 UTC 日期切错。
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import main
from models import Area, Child, ClassRoom, Observation, ObservationChild, Teacher

UTC = timezone.utc


def _bj_hour(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    """给定北京自然日时刻，返回对应的 UTC datetime（观测时间以 UTC 落库）。

    北京时间 = UTC + 8：北京 09-03 00:30 对应的 UTC 时刻是 09-02 16:30。
    """
    from datetime import timedelta

    naive_utc = datetime(2026, 9, day, hour, minute, second)
    return (naive_utc - timedelta(hours=8)).replace(tzinfo=UTC)


class ObservationSearchTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ai_mode_patcher = patch.object(main.ai_service, "AI_MODE", "mock")
        self.ai_mode_patcher.start()
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
            self.block_area = Area(code="construction", name="建构区")
            self.role_area = Area(code="role", name="角色区")
            room = ClassRoom(name="中二班", age_group="middle")
            session.add(self.block_area)
            session.add(self.role_area)
            session.add(room)
            session.commit()
            session.refresh(self.block_area)
            session.refresh(self.role_area)
            session.refresh(room)
            self.teacher = Teacher(name="测试教师", classroom_id=room.id)
            self.child_a = Child(name="测试幼儿A", classroom_id=room.id, gender="女")
            self.child_b = Child(name="测试幼儿B", classroom_id=room.id, gender="男")
            session.add(self.teacher)
            session.add(self.child_a)
            session.add(self.child_b)
            session.commit()
            session.refresh(self.teacher)
            session.refresh(self.child_a)
            session.refresh(self.child_b)
            self.area_id = self.block_area.id
            self.role_area_id = self.role_area.id
            self.child_a_id = self.child_a.id
            self.child_b_id = self.child_b.id

    def tearDown(self):
        self.ai_mode_patcher.stop()
        self.temp_dir.cleanup()

    def add_observation(
        self,
        observed_at,
        area_id=None,
        child_id=None,
        status="confirmed",
        related_children=(),
        note=None,
    ):
        """直接落库一条记录；related_children 用于构造多人关联。"""
        with Session(main.engine) as session:
            observation = Observation(
                child_id=child_id,
                area_id=area_id if area_id is not None else self.area_id,
                classroom_id=1,
                observer_id=self.teacher.id,
                observed_at=observed_at,
                age_group="middle",
                status=status,
                note=note,
            )
            session.add(observation)
            session.flush()
            links = []
            if child_id is not None:
                links.append(ObservationChild(
                    observation_id=observation.id,
                    child_id=child_id,
                    is_primary=True,
                ))
            for child in related_children:
                links.append(ObservationChild(
                    observation_id=observation.id,
                    child_id=child,
                    is_primary=False,
                ))
            session.add_all(links)
            session.commit()
            return observation.id

    def ids(self, response):
        self.assertEqual(response.status_code, 200)
        return [item["id"] for item in response.json()]

    # ---------- 幼儿过滤 ----------

    def test_child_filter_keeps_legacy_primary_and_related_children(self):
        legacy_id = self.add_observation(
            _bj_hour(1, 9, 0), child_id=self.child_a_id
        )
        related_id = self.add_observation(
            _bj_hour(1, 10, 0),
            child_id=self.child_b_id,
            related_children=(self.child_a_id,),
        )
        other_id = self.add_observation(
            _bj_hour(1, 11, 0), child_id=self.child_b_id
        )

        # A 是 legacy 主角（只写了 child_id）也是另一条的关联幼儿 → 两条都命中
        for_a = self.ids(
            self.client.get("/observations", params={"child_id": self.child_a_id})
        )
        self.assertEqual(sorted(for_a), sorted([legacy_id, related_id]))
        self.assertNotIn(other_id, for_a)

        for_b = self.ids(
            self.client.get("/observations", params={"child_id": self.child_b_id})
        )
        self.assertEqual(sorted(for_b), sorted([related_id, other_id]))
        self.assertNotIn(legacy_id, for_b)

    # ---------- 区域与组合 ----------

    def test_area_filter_and_combined_with_child_and_status(self):
        block_only = self.add_observation(
            _bj_hour(1, 9, 0), child_id=self.child_a_id, area_id=self.area_id
        )
        self.add_observation(
            _bj_hour(1, 9, 30),
            child_id=self.child_a_id,
            area_id=self.role_area_id,
        )
        draft = self.add_observation(
            _bj_hour(2, 9, 0),
            child_id=self.child_a_id,
            area_id=self.area_id,
            status="ready_for_review",
        )

        by_area = self.ids(
            self.client.get("/observations", params={"area_id": self.area_id})
        )
        self.assertEqual(sorted(by_area), sorted([block_only, draft]))

        combined = self.ids(self.client.get(
            "/observations",
            params={"area_id": self.area_id, "child_id": self.child_a_id,
                    "status": "confirmed"},
        ))
        self.assertEqual(combined, [block_only])

    # ---------- 日期区间（北京时间自然日） ----------

    def build_date_ladder(self):
        """北京自然日：09-02 一晚、09-03 三个时刻、09-04 一晚。"""
        return {
            "before": self.add_observation(_bj_hour(2, 23, 30)),   # 09-02 23:30
            "midnight": self.add_observation(_bj_hour(3, 0, 30)),  # 09-03 00:30（UTC 09-02 16:30）
            "morning": self.add_observation(_bj_hour(3, 9, 30)),   # 09-03 09:30
            "night": self.add_observation(_bj_hour(3, 23, 30)),    # 09-03 23:30
            "after": self.add_observation(_bj_hour(4, 0, 30)),     # 09-04 00:30（UTC 09-03 16:30）
        }

    def test_date_range_uses_kindergarten_local_days(self):
        ladder = self.build_date_ladder()
        only_day = self.ids(self.client.get(
            "/observations",
            params={"date_from": "2026-09-03", "date_to": "2026-09-03"},
        ))
        self.assertEqual(
            sorted(only_day),
            sorted([ladder["midnight"], ladder["morning"], ladder["night"]]),
        )

    def test_date_from_only_and_date_to_only(self):
        ladder = self.build_date_ladder()
        from_0303 = self.ids(self.client.get(
            "/observations", params={"date_from": "2026-09-03"}
        ))
        self.assertEqual(
            sorted(from_0303),
            sorted([ladder["midnight"], ladder["morning"],
                    ladder["night"], ladder["after"]]),
        )
        to_0303 = self.ids(self.client.get(
            "/observations", params={"date_to": "2026-09-03"}
        ))
        self.assertEqual(
            sorted(to_0303),
            sorted([ladder["before"], ladder["midnight"],
                    ladder["morning"], ladder["night"]]),
        )

    def test_time_and_child_can_be_combined(self):
        ladder = self.build_date_ladder()
        other_child = self.add_observation(_bj_hour(3, 10, 0),
                                           child_id=self.child_a_id)
        mine = self.add_observation(_bj_hour(3, 11, 0),
                                    child_id=self.child_b_id)
        # 只查 09-03 且属于 child_b → mine，不含同区间的 other_child
        result = self.ids(self.client.get(
            "/observations",
            params={"date_from": "2026-09-03", "date_to": "2026-09-03",
                    "child_id": self.child_b_id},
        ))
        self.assertEqual(result, [mine])
        self.assertNotIn(other_child, result)
        self.assertNotIn(ladder["before"], result)

    # ---------- 参数校验 ----------

    def test_date_range_validation_and_missing_references(self):
        bad_range = self.client.get(
            "/observations",
            params={"date_from": "2026-09-05", "date_to": "2026-09-03"},
        )
        self.assertEqual(bad_range.status_code, 422)
        self.assertIn("date_from", bad_range.json()["detail"])

        missing_child = self.client.get(
            "/observations", params={"child_id": 999999}
        )
        self.assertEqual(missing_child.status_code, 404)
        self.assertIn("999999", missing_child.json()["detail"])

        missing_area = self.client.get(
            "/observations", params={"area_id": 999999}
        )
        self.assertEqual(missing_area.status_code, 404)
        self.assertIn("999999", missing_area.json()["detail"])

    # ---------- 回归：无过滤与状态过滤保持原行为 ----------

    def test_no_filter_returns_all_and_status_still_works(self):
        a = self.add_observation(_bj_hour(1, 9, 0), status="confirmed")
        b = self.add_observation(_bj_hour(1, 10, 0), status="ready_for_review")
        self.assertEqual(
            sorted(self.ids(self.client.get("/observations"))), sorted([a, b])
        )
        drafts = self.ids(self.client.get(
            "/observations", params={"status": "ready_for_review"}
        ))
        self.assertEqual(drafts, [b])


if __name__ == "__main__":
    unittest.main()
