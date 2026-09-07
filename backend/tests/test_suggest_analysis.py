import unittest
from unittest.mock import patch

import ai_service


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class SuggestAnalysisTest(unittest.TestCase):
    def test_mock_returns_scaffold_with_indicator_names(self):
        with patch.object(ai_service, "AI_MODE", "mock"):
            out = ai_service.suggest_analysis_and_strategy(
                narrative="幼儿A先搬来积木，接着拼成圆形。",
                area_name="建构区",
                indicator_names=["身体行为参与度", "身体行为目的性"],
            )
        self.assertTrue(out["is_mock"])
        self.assertTrue(out["analysis"].strip())
        self.assertTrue(out["strategy"].strip())
        self.assertIn("建构区", out["analysis"])
        self.assertIn("身体行为参与度", out["analysis"])
        self.assertIn("ai_run", out)
        self.assertNotIn("ai_run", out.get("analysis", 0) or {})  # 分析不含 ai_run

    def test_deepseek_success_returns_parsed(self):
        payload = {
            "choices": [{"message": {"content": '{"analysis":"幼儿搭积木由简到繁。","strategy":"提供更多积木。"}'}}],
            "usage": {"total_tokens": 20},
        }
        with patch.object(ai_service, "AI_MODE", "deepseek"), patch.object(ai_service, "DEEPSEEK_API_KEY", "dk-test"):
            with patch.object(ai_service.httpx, "post", return_value=FakeResponse(payload)):
                out = ai_service.suggest_analysis_and_strategy(
                    narrative="幼儿A搭积木。",
                    area_name="建构区",
                    indicator_names=["身体行为参与度"],
                )
        self.assertFalse(out["is_mock"])
        self.assertEqual(out["analysis"], "幼儿搭积木由简到繁。")
        self.assertEqual(out["strategy"], "提供更多积木。")
        self.assertEqual(out["engine"], ai_service.DEEPSEEK_MODEL)

    def test_deepseek_failure_falls_back_to_mock(self):
        with patch.object(ai_service, "AI_MODE", "deepseek"), patch.object(ai_service, "DEEPSEEK_API_KEY", "dk-test"):
            with patch.object(ai_service.httpx, "post", side_effect=Exception("boom")):
                out = ai_service.suggest_analysis_and_strategy(
                    narrative="幼儿A搭积木。",
                    area_name="建构区",
                    indicator_names=[],
                )
        self.assertTrue(out["is_mock"])
        self.assertTrue(out["analysis"].strip())
        self.assertTrue(out["strategy"].strip())


if __name__ == "__main__":
    unittest.main()
