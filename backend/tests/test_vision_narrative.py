"""工作流 A 豆包视觉白描的单元测试（mock httpx，不发真实请求、不使用真实 Key）。"""

import unittest
from unittest.mock import patch

import ai_service
from ai_service import generate_narrative


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


FAKE_IMAGE = "data:image/jpeg;base64,aGVsbG8="  # 模拟图片 data URI


class DoubaoVisionNarrativeTest(unittest.TestCase):
    def _setup(self, ark_key="ark-test", vision_mode="doubao"):
        patchers = [
            patch.object(ai_service, "ARK_API_KEY", ark_key),
            patch.object(ai_service, "VISION_MODE", vision_mode),
        ]
        for p in patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patchers])

    def test_builds_responses_request_and_parses_text(self):
        self._setup()
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse({
                "id": "resp_1",
                "object": "response",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "幼儿A坐在积木区，拿起两块红色积木。"},
                        ],
                    }
                ],
            })

        with patch.object(ai_service.httpx, "post", fake_post):
            result = generate_narrative(
                area_code="construction",
                area_name="建构区",
                media_type="video",
                duration_sec=300,
                frames=[{"timestamp_sec": None, "data_uri": FAKE_IMAGE}],
                purpose="观察搭建倒塌后如何调整",
                subject_context="幼儿A是左侧红衣幼儿",
            )

        # 请求格式校验（火山方舟 Responses API）
        body = captured["json"]
        self.assertEqual(body["model"], ai_service.DOUBAO_VISION_MODEL)
        content = body["input"][0]["content"]
        self.assertEqual(content[0]["type"], "input_image")
        self.assertEqual(content[0]["image_url"], FAKE_IMAGE)
        self.assertEqual(content[1]["type"], "input_text")
        self.assertIn("建构区", content[1]["text"])
        self.assertIn("观察搭建倒塌后如何调整", content[1]["text"])
        self.assertIn("幼儿A是左侧红衣幼儿", content[1]["text"])
        self.assertIn("不能作为已发生行为或能力的证据", content[1]["text"])
        self.assertIn("不得按出镜频率猜人", content[1]["text"])
        # 鉴权头用的是 ARK_API_KEY
        self.assertEqual(captured["headers"]["Authorization"], "Bearer ark-test")
        self.assertEqual(captured["url"], ai_service.DOUBAO_VISION_API_URL)

        # 返回契约
        self.assertEqual(result["narrative"], "幼儿A坐在积木区，拿起两块红色积木。")
        self.assertFalse(result["is_mock"])
        self.assertEqual(result["engine"], ai_service.DOUBAO_VISION_MODEL)
        self.assertTrue(result["notice"])
        self.assertEqual(result["ai_run"]["provider"], "doubao")
        self.assertEqual(result["ai_run"]["status"], "completed")
        self.assertFalse(result["ai_run"]["is_mock"])

    def test_falls_back_to_mock_when_request_errors(self):
        self._setup()

        def fake_post(url, headers=None, json=None, timeout=None):
            raise ai_service.httpx.ConnectError("connection refused")

        with patch.object(ai_service.httpx, "post", fake_post):
            result = generate_narrative(
                area_code="sand_water",
                media_type="photo",
                frames=[{"timestamp_sec": None, "data_uri": FAKE_IMAGE}],
            )
        self.assertTrue(result["is_mock"])
        self.assertEqual(result["engine"], "demo-mock-v1")
        self.assertEqual(result["ai_run"]["status"], "failed")
        self.assertTrue(result["ai_run"]["is_mock"])
        self.assertIn("失败", result["ai_run"]["error_reason"])

    def test_video_multiple_frames_are_sent_in_order(self):
        self._setup()
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["json"] = json
            return FakeResponse({
                "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "幼儿A先搬来积木，接着拼成圆形。"},
                ]}],
            })

        frames = [
            {"timestamp_sec": 0, "data_uri": "data:image/png;base64,aw=="},
            {"timestamp_sec": 15, "data_uri": "data:image/png;base64,bg=="},
            {"timestamp_sec": 29, "data_uri": "data:image/png;base64,cg=="},
        ]
        with patch.object(ai_service.httpx, "post", fake_post):
            result = generate_narrative(
                area_code="construction",
                area_name="建构区",
                media_type="video",
                duration_sec=30,
                frames=frames,
            )
        content = captured["json"]["input"][0]["content"]
        # 3 帧画面 + 1 段文字引导
        self.assertEqual([c["type"] for c in content], ["input_image", "input_image", "input_image", "input_text"])
        self.assertEqual([c["image_url"] for c in content[:3]], [f["data_uri"] for f in frames])
        # 提示词应引导模型按时间顺序、连贯地描述（不是点状罗列）
        self.assertIn("连贯的白描", content[3]["text"])
        self.assertIn("起因", content[3]["text"])

    def test_falls_back_without_key_or_image(self):
        # 无 key：不调用模型直接降级
        self._setup(ark_key="")
        with patch.object(ai_service.httpx, "post") as post:
            result = generate_narrative(
                area_code="construction",
                media_type="video",
                frames=[{"timestamp_sec": None, "data_uri": FAKE_IMAGE}],
            )
            post.assert_not_called()
        self.assertTrue(result["is_mock"])

        # 无图：不调用模型直接降级
        self._setup(ark_key="ark-test")
        with patch.object(ai_service.httpx, "post") as post:
            result = generate_narrative(
                area_code="construction",
                media_type="video",
                frames=None,
            )
            post.assert_not_called()
        self.assertTrue(result["is_mock"])

    def test_mock_mode_returns_mock_without_ai_run(self):
        self._setup(vision_mode="mock")
        with patch.object(ai_service.httpx, "post") as post:
            result = generate_narrative(
                area_code="roleplay",
                media_type="photo",
                frames=[{"timestamp_sec": None, "data_uri": FAKE_IMAGE}],
            )
            post.assert_not_called()
        self.assertTrue(result["is_mock"])
        self.assertNotIn("ai_run", result)


if __name__ == "__main__":
    unittest.main()
