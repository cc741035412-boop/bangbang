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


class SuggestedFrameCountTest(unittest.TestCase):
    def test_short_clips_get_fewer_frames(self):
        self.assertEqual(main.suggested_frame_count(8), 4)
        self.assertEqual(main.suggested_frame_count(12), 6)
        self.assertEqual(main.suggested_frame_count(20), 6)
        self.assertEqual(main.suggested_frame_count(45), 10)

    def test_longer_clips_are_denser(self):
        self.assertEqual(main.suggested_frame_count(90), 16)
        self.assertEqual(main.suggested_frame_count(150), 20)
        self.assertEqual(main.suggested_frame_count(180), 20)

    def test_unknown_duration_returns_default(self):
        self.assertEqual(main.suggested_frame_count(None), 10)
        self.assertEqual(main.suggested_frame_count(0), 10)

    def test_monotonic_with_duration(self):
        # 帧数随时长只增不减，避免长视频反而抽得更少
        for a, b in [(8, 20), (20, 45), (45, 90), (90, 150), (150, 180)]:
            self.assertLessEqual(main.suggested_frame_count(a), main.suggested_frame_count(b))


class SelectTimestampsTest(unittest.TestCase):
    def test_prefers_content_change_points_and_keeps_first_last(self):
        ts = main._select_timestamps(10.0, 5, [3.0, 7.0])
        self.assertIn(3.0, ts)
        self.assertIn(7.0, ts)
        self.assertEqual(ts[0], 0.0)
        self.assertEqual(ts[-1], 9.9)  # duration - 0.1
        self.assertEqual(ts, sorted(ts))
        # 最小间距 = duration/count，故最多 floor(10/2)+1 个点
        self.assertLessEqual(len(ts), 5)
        for a, b in zip(ts, ts[1:]):
            self.assertGreaterEqual(b - a, 10.0 / 5 - 1e-6)

    def test_empty_change_points_fills_evenly(self):
        ts = main._select_timestamps(10.0, 4, [])
        self.assertEqual(len(ts), 4)
        self.assertEqual(ts[0], 0.0)
        self.assertLessEqual(ts[-1], 9.9)

    def test_dense_change_points_respect_min_spacing(self):
        ts = main._select_timestamps(10.0, 3, [1.0, 1.2, 1.4, 5.0])
        self.assertEqual(len(ts), 3)
        # 间距至少 duration/count
        for a, b in zip(ts, ts[1:]):
            self.assertGreaterEqual(b - a, 10.0 / 3 - 1e-6)


class ContentChangeDetectionTest(unittest.TestCase):
    def test_detects_scene_cut_near_midpoint(self):
        import subprocess
        import imageio_ffmpeg
        try:
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            self.skipTest(f"imageio-ffmpeg 不可用: {e}")
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "cut.mp4"
            r = subprocess.run(
                [exe, "-y",
                 "-f", "lavfi", "-i", "color=red:duration=2:size=160x120:rate=10",
                 "-f", "lavfi", "-i", "color=blue:duration=2:size=160x120:rate=10",
                 "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(video)],
                capture_output=True, timeout=120,
            )
            if r.returncode != 0:
                self.skipTest("无法生成场景切换测试视频")
            change_ts = main._content_change_timestamps(exe, video, 4.0, 10)
            self.assertTrue(change_ts, "应检测到场景切换时刻")
            self.assertTrue(
                any(abs(t - 2.0) < 0.8 for t in change_ts),
                f"切换点应在 2.0s 附近，got {change_ts}",
            )


class ExtractHighlightFrameTest(unittest.TestCase):
    def test_extracts_a_png_frames_from_video(self):
        import subprocess
        import imageio_ffmpeg
        try:
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            self.skipTest(f"imageio-ffmpeg 不可用: {e}")
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "clip.mp4"
            r = subprocess.run(
                [exe, "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=10",
                 "-pix_fmt", "yuv420p", str(video)],
                capture_output=True, timeout=120,
            )
            if r.returncode != 0:
                self.skipTest("无法生成测试视频")
            frames = main.extract_highlight_frames(video, max_frames=3)
            self.assertGreaterEqual(len(frames), 1, "应抽到至少 1 帧")
            from PIL import Image as _Img
            from io import BytesIO as _BIO
            for frame in frames:
                self.assertTrue(frame.startswith(b"\x89PNG") or frame.startswith(b"\xff\xd8"))
                _Img.open(_BIO(frame)).verify()


class PrepareExportPhotoTest(unittest.TestCase):
    def test_converts_heic_phone_photo_to_document_safe_jpeg(self):
        from pillow_heif import from_pillow

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "phone-photo.heic"
            from_pillow(Image.new("RGB", (80, 60), color="green")).save(source)

            prepared = main.prepare_export_photo(source)

        self.assertIsNotNone(prepared)
        self.assertTrue(prepared.startswith(b"\xff\xd8"))
        Image.open(BytesIO(prepared)).verify()


if __name__ == "__main__":
    unittest.main()
