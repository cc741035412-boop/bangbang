import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import main
from models import AIRun, Area, Child, ClassRoom, Observation, ObservationTag


class ObservationStatusFlowTest(unittest.TestCase):
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
        self.ai_mode_patcher.stop()
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
        self.assertEqual(narrative.json()["status"], "ready_for_review")
        self.assertIsNotNone(narrative.json()["processing_started_at"])
        self.assertIsNotNone(narrative.json()["ready_at"])
        self.assertTrue(narrative.json()["is_mock"])

        suggestions = self.client.post(f"/observations/{observation_id}/suggest-tags")
        self.assertEqual(suggestions.status_code, 200)
        self.assertEqual(suggestions.json()["status"], "ready_for_review")
        self.assertIsNotNone(suggestions.json()["ready_at"])
        self.assertTrue(suggestions.json()["suggestions"])
        self.assertTrue(suggestions.json()["quant_hits"])
        with Session(main.engine) as session:
            mock_run = session.get(AIRun, suggestions.json()["ai_run_id"])
            self.assertEqual(mock_run.status, "completed")
            self.assertTrue(mock_run.is_mock)
            self.assertEqual(mock_run.provider, "mock")

        detail_with_tags = self.client.get(f"/observations/{observation_id}").json()
        system_tags = [
            tag for tag in detail_with_tags["tags"]
            if tag["source"] == "system_determined"
        ]
        self.assertTrue(system_tags)
        self.assertTrue(all(tag["accepted"] is True for tag in system_tags))

        cancelled_system = self.client.patch(
            f"/observations/{observation_id}/tags/{system_tags[0]['id']}",
            json={"accepted": False},
        )
        self.assertEqual(cancelled_system.status_code, 200)
        restored_detail = self.client.get(f"/observations/{observation_id}").json()
        restored_system = next(
            tag for tag in restored_detail["tags"] if tag["id"] == system_tags[0]["id"]
        )
        self.assertFalse(restored_system["accepted"])

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

        second_tag_id = suggestions.json()["suggestions"][1]["tag_id"]
        rejected = self.client.patch(
            f"/observations/{observation_id}/tags/{second_tag_id}",
            json={"accepted": False},
        )
        self.assertEqual(rejected.status_code, 200)

        metrics = self.client.get("/metrics/ai-quality").json()
        self.assertEqual(metrics["AI建议总数"], 3)
        self.assertEqual(metrics["教师已处理"], 2)
        self.assertEqual(metrics["教师采纳"], 1)
        self.assertEqual(metrics["采纳率"], 0.5)

        confirmed = self.client.post(f"/observations/{observation_id}/confirm")
        self.assertEqual(confirmed.status_code, 200)
        confirmed_observation = confirmed.json()["observation"]
        self.assertEqual(confirmed_observation["status"], "confirmed")
        self.assertIsNotNone(confirmed_observation["confirmed_at"])
        detail = self.client.get(f"/observations/{observation_id}").json()
        self.assertEqual(detail["child_confirmed_count"], 1)

    def test_confirmation_requires_child_without_changing_age_snapshot(self):
        created = self.client.post("/observations", json={"area_id": self.area_id}).json()
        media = self.client.post(
            "/uploads",
            files={"file": ("mock.mp4", b"mock-video", "video/mp4")},
        ).json()
        self.client.post(
            f"/observations/{created['id']}/attach-media",
            params={"media_id": media["id"]},
        )
        self.client.post(f"/observations/{created['id']}/narrative")
        suggestions = self.client.post(
            f"/observations/{created['id']}/suggest-tags"
        ).json()
        self.client.patch(
            f"/observations/{created['id']}/tags/{suggestions['suggestions'][0]['tag_id']}",
            json={"accepted": True},
        )

        missing_child = self.client.post(f"/observations/{created['id']}/confirm")
        self.assertEqual(missing_child.status_code, 400)
        self.assertEqual(
            missing_child.json()["detail"],
            "请先选择这条记录关于哪位幼儿",
        )

        original_classroom_id = created["classroom_id"]
        original_age_group = created["age_group"]
        patched = self.client.patch(
            f"/observations/{created['id']}",
            json={"child_id": self.child_id},
        ).json()
        self.assertEqual(patched["classroom_id"], original_classroom_id)
        self.assertEqual(patched["age_group"], original_age_group)

        confirmed = self.client.post(f"/observations/{created['id']}/confirm")
        self.assertEqual(confirmed.status_code, 200)
        self.assertIsNotNone(confirmed.json()["observation"]["confirmed_at"])

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
        self.assertEqual(retried.json()["status"], "ready_for_review")
        self.assertIsNotNone(retried.json()["ready_at"])

    def test_processing_status_is_visible_while_ai_is_running(self):
        observation_id = self.create_bound_observation()
        started = threading.Event()
        release = threading.Event()
        original_generate = main.ai_service.generate_narrative

        def slow_generate(*args, **kwargs):
            started.set()
            self.assertTrue(release.wait(timeout=2))
            return original_generate(*args, **kwargs)

        with patch.object(main.ai_service, "generate_narrative", side_effect=slow_generate):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.client.post,
                    f"/observations/{observation_id}/narrative",
                )
                self.assertTrue(started.wait(timeout=2))
                processing = self.client.get(f"/observations/{observation_id}")
                self.assertEqual(processing.json()["status"], "processing")
                self.assertIsNotNone(processing.json()["processing_started_at"])
                self.assertIsNone(processing.json()["ready_at"])
                release.set()
                completed = future.result(timeout=2)

        self.assertEqual(completed.json()["status"], "ready_for_review")
        self.assertIsNotNone(completed.json()["ready_at"])

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

    def test_deepseek_suggestions_are_validated_audited_and_linked(self):
        observation_id = self.create_bound_observation()
        self.client.post(f"/observations/{observation_id}/narrative")
        model_content = {
            "suggestions": [
                {
                    "indicator_code": "4.4",
                    "indicator_name": "模型不能决定名称",
                    "level": 2,
                    "level_desc": "模型不能决定描述",
                    "confidence": 0.86,
                    "reason": "白描原文写道：“调整了间距后继续摆放”",
                    "evidence_based": True,
                    "rank": 9,
                },
                {
                    "indicator_code": "1.2",
                    "indicator_name": "身体探索方式",
                    "level": 3,
                    "level_desc": "无效描述",
                    "confidence": 0.8,
                    "reason": "白描原文写道：“白描中不存在的片段”",
                    "evidence_based": True,
                    "rank": 1,
                },
                {
                    "indicator_code": "2.1",
                    "indicator_name": "伦理禁区",
                    "level": 1,
                    "level_desc": "不应出现",
                    "confidence": 0.9,
                    "reason": "白描原文写道：“幼儿A坐在地垫上”",
                    "evidence_based": True,
                    "rank": 2,
                },
            ]
        }
        raw_response = {
            "id": "test-completion",
            "choices": [{
                "message": {"content": json.dumps(model_content, ensure_ascii=False)}
            }],
            "usage": {
                "prompt_tokens": 1200,
                "completion_tokens": 180,
                "total_tokens": 1380,
            },
        }
        response = httpx.Response(
            200,
            json=raw_response,
            request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"),
        )

        with (
            patch.object(main.ai_service, "AI_MODE", "deepseek"),
            patch.object(main.ai_service, "DEEPSEEK_API_KEY", "test-key"),
            patch.object(main.ai_service.httpx, "post", return_value=response) as post,
        ):
            generated = self.client.post(
                f"/observations/{observation_id}/suggest-tags"
            )

        self.assertEqual(generated.status_code, 200)
        body = generated.json()
        self.assertFalse(body["is_mock"])
        self.assertEqual([item["indicator_code"] for item in body["suggestions"]], ["4.4", "1.2"])
        self.assertTrue(body["suggestions"][0]["evidence_based"])
        self.assertEqual(
            body["suggestions"][0]["reason"],
            "白描原文：“调整了间距后继续摆放”",
        )
        self.assertFalse(body["suggestions"][1]["evidence_based"])
        self.assertEqual(body["suggestions"][1]["confidence"], 0.42)

        request_body = post.call_args.kwargs["json"]
        self.assertEqual(request_body["model"], "deepseek-chat")
        self.assertEqual(request_body["temperature"], 1.0)
        self.assertEqual(request_body["response_format"], {"type": "json_object"})
        rendered = request_body["messages"][1]["content"]
        self.assertIn('"indicator_code": "4.4"', rendered)
        self.assertNotIn('"indicator_code": "2.1"', rendered)

        with Session(main.engine) as session:
            run = session.get(AIRun, body["ai_run_id"])
            self.assertEqual(run.status, "completed")
            self.assertEqual(run.prompt_version, "wf-b-v1")
            self.assertEqual(run.temperature, 1.0)
            self.assertEqual(run.token_usage["total_tokens"], 1380)
            self.assertIn("2.1", run.error_reason)
            self.assertIn("原文引用无法", run.error_reason)
            tags = session.exec(
                select(ObservationTag).where(
                    ObservationTag.observation_id == observation_id
                )
            ).all()
            self.assertTrue(tags)
            self.assertTrue(all(tag.ai_run_id == run.id for tag in tags))

    def test_deepseek_auth_failure_retries_once_and_falls_back(self):
        observation_id = self.create_bound_observation()
        self.client.post(f"/observations/{observation_id}/narrative")
        unauthorized = httpx.Response(
            401,
            json={"error": {"message": "Authentication Fails"}},
            request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"),
        )

        with (
            patch.object(main.ai_service, "AI_MODE", "deepseek"),
            patch.object(main.ai_service, "DEEPSEEK_API_KEY", "wrong-key"),
            patch.object(
                main.ai_service.httpx,
                "post",
                return_value=unauthorized,
            ) as post,
        ):
            generated = self.client.post(
                f"/observations/{observation_id}/suggest-tags"
            )

        self.assertEqual(generated.status_code, 200)
        body = generated.json()
        self.assertTrue(body["is_mock"])
        self.assertEqual(post.call_count, 2)
        self.assertTrue(body["suggestions"])

        with Session(main.engine) as session:
            run = session.get(AIRun, body["ai_run_id"])
            self.assertEqual(run.status, "failed")
            self.assertTrue(run.is_mock)
            self.assertIn("401", run.error_reason)
            tags = session.exec(
                select(ObservationTag).where(
                    ObservationTag.observation_id == observation_id
                )
            ).all()
            self.assertTrue(all(tag.ai_run_id == run.id for tag in tags))


if __name__ == "__main__":
    unittest.main()
