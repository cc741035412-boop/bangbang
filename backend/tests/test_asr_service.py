"""ASR 转写服务单测：不发真实请求、不用真实 Key。"""

import os
import tempfile
import unittest
from unittest.mock import patch

import config
import asr_service


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _fake_payload(text):
    return {"choices": [{"message": {"content": text}}], "usage": {"total_tokens": 100}}


class AsrServiceTest(unittest.TestCase):
    def _set_doubao(self, key="ark-test"):
        patchers = [
            patch.object(config, "ASR_MODE", "doubao"),
            patch.object(config, "ASR_API_KEY", key),
            patch.object(config, "ASR_MODEL", "ep-test"),
            patch.object(asr_service, "_extract_audio_bytes", lambda p: b"RIFF....wav"),
        ]
        for p in patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patchers])

    def test_mock_mode_returns_mock(self):
        with patch.object(config, "ASR_MODE", "mock"):
            out = asr_service.transcribe_video("/tmp/whatever.mp4")
        self.assertTrue(out["is_mock"])
        self.assertIsNone(out["transcript"])
        self.assertIsNone(out["asr_run"])

    def test_doubao_success_returns_transcript(self):
        self._set_doubao()
        with patch.object(asr_service.httpx, "post", return_value=FakeResponse(_fake_payload("孩子们在搭桥"))):
            out = asr_service.transcribe_video("/tmp/a.mp4")
        self.assertFalse(out["is_mock"])
        self.assertEqual(out["transcript"], "孩子们在搭桥")
        self.assertIsNotNone(out["asr_run"])

    def test_doubao_empty_output_falls_back_to_none(self):
        self._set_doubao()
        with patch.object(asr_service.httpx, "post", return_value=FakeResponse(_fake_payload("   "))):
            out = asr_service.transcribe_video("/tmp/a.mp4")
        self.assertFalse(out["is_mock"])
        self.assertIsNone(out["transcript"])  # 空串 → None（无语音）

    def test_doubao_failure_degrades_to_mock(self):
        self._set_doubao()
        with patch.object(asr_service.httpx, "post", side_effect=Exception("boom")):
            out = asr_service.transcribe_video("/tmp/a.mp4")
        self.assertTrue(out["is_mock"])
        self.assertIsNone(out["transcript"])

    def test_no_key_degrades_to_mock(self):
        self._set_doubao(key="")
        out = asr_service.transcribe_video("/tmp/a.mp4")
        self.assertTrue(out["is_mock"])

    def test_extract_audio_from_video_with_audio(self):
        import subprocess
        import imageio_ffmpeg
        try:
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            self.skipTest(f"imageio-ffmpeg 不可用: {e}")
        with tempfile.TemporaryDirectory() as d:
            mp4 = os.path.join(d, "probe.mp4")
            r = subprocess.run(
                [exe, "-y",
                 "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                 "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                 "-shortest", "-pix_fmt", "yuv420p", mp4],
                capture_output=True, timeout=120,
            )
            if r.returncode != 0:
                self.skipTest("无法生成带音频的测试视频")
            audio = asr_service._extract_audio_bytes(mp4)
            self.assertTrue(audio and len(audio) > 100)


if __name__ == "__main__":
    unittest.main()
