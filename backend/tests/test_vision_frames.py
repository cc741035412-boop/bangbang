"""工作流 A 视频抽帧的空白帧检测 / 重采样逻辑测试。

覆盖 main._frame_is_blank / main._blank_fallback_offsets / main._extract_video_frames，
不发真实模型请求。视频集成用例用 ffmpeg 生成一段"有内容 + 黑尾"的测试视频，
若本机无法生成测试视频则跳过该用例（不影响确定性单测覆盖）。
"""

import base64
import subprocess
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

import main


def _png_data_uri(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _black_img(size=(64, 64)) -> Image.Image:
    return Image.new("L", size, 0)


def _white_img(size=(64, 64)) -> Image.Image:
    return Image.new("L", size, 255)


def _varied_img(size=(64, 64)) -> Image.Image:
    img = Image.new("L", size, 0)
    px = img.load()
    for y in range(size[1]):
        for x in range(size[0]):
            px[x, y] = (x * 4 + y * 2) % 256
    return img


class FrameIsBlankTest(unittest.TestCase):
    def test_black_frame_is_blank(self):
        self.assertTrue(main._frame_is_blank(_png_data_uri(_black_img())))

    def test_white_frame_is_blank(self):
        self.assertTrue(main._frame_is_blank(_png_data_uri(_white_img())))

    def test_varied_frame_not_blank(self):
        self.assertFalse(main._frame_is_blank(_png_data_uri(_varied_img())))

    def test_invalid_data_uri_returns_false(self):
        self.assertFalse(main._frame_is_blank("not-a-data-uri"))


class FallbackOffsetsTest(unittest.TestCase):
    def test_start_frame_searches_forward(self):
        offs = main._blank_fallback_offsets(0.05, 10)
        self.assertTrue(offs)
        self.assertTrue(all(o > 0 for o in offs))

    def test_end_frame_searches_backward(self):
        offs = main._blank_fallback_offsets(9.9, 10)
        self.assertTrue(offs)
        self.assertTrue(all(o < 0 for o in offs))

    def test_middle_frame_interleaves_and_bounded(self):
        offs = main._blank_fallback_offsets(5.0, 10, max_search=3)
        self.assertEqual(offs, [1.0, -1.0, 2.0])

    def test_respects_max_search(self):
        offs = main._blank_fallback_offsets(5.0, 10)
        self.assertLessEqual(len(offs), 8)


class ExtractVideoFramesIntegrationTest(unittest.TestCase):
    def _make_video_with_black_tail(self, path: Path) -> None:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            exe, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=10",
            "-f", "lavfi", "-i", "color=black:duration=1:size=320x240:rate=10",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
            "-pix_fmt", "yuv420p", str(path),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[:500])

    def test_skips_black_tail(self):
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "clip.mp4"
            try:
                self._make_video_with_black_tail(video)
            except Exception as e:  # 环境无法生成测试视频时跳过，不硬断
                self.skipTest(f"ffmpeg 生成测试视频失败: {e}")
            frames = main._extract_video_frames(video, count=3)
            self.assertTrue(frames, "应能抽到帧")
            # 黑屏段在 3.0~4.0s，末帧应被重采样到黑屏之前（<3.0s）
            self.assertLess(frames[-1]["timestamp_sec"], 3.0)
            for f in frames:
                self.assertFalse(main._frame_is_blank(f["data_uri"]),
                                 "不应保留空白帧")
            # 帧按时间升序
            stamps = [f["timestamp_sec"] for f in frames]
            self.assertEqual(stamps, sorted(stamps))

    def test_extract_ten_frames_evenly(self):
        import subprocess
        import imageio_ffmpeg
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            self.skipTest(f"imageio-ffmpeg 不可用: {e}")
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "plain.mp4"
            r = subprocess.run(
                [exe, "-y", "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=10",
                 "-pix_fmt", "yuv420p", str(video)],
                capture_output=True, timeout=120,
            )
            if r.returncode != 0:
                self.skipTest("无法生成测试视频")
            frames = main._extract_video_frames(video, count=10)
            self.assertGreaterEqual(len(frames), 8, "应采到接近 10 帧")
            stamps = [f["timestamp_sec"] for f in frames]
            self.assertEqual(stamps, sorted(stamps))
            self.assertEqual(stamps[0], 0.0)
            self.assertLess(stamps[-1], 5.0)
            for f in frames:
                self.assertFalse(main._frame_is_blank(f["data_uri"]))


if __name__ == "__main__":
    unittest.main()
