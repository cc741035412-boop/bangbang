"""工作流 A 配套：把观察视频里的语音转成文字（ASR），供白描引用对话。

实现：用火山方舟豆包多模态模型，复用与视觉同一把 `ark-` Key，
把音频以 base64 `input_audio` 直接交给模型，**不需要公网 URL / 对象存储**。

对外入口：`transcribe_video(video_path) -> dict`
返回：
    {"transcript": str|None, "is_mock": bool, "notice": str, "asr_run": dict|None}
- transcript 为去空白后的转写文本；无语音或失败时为 None（白描降级为"无音频"）。
- 失败一律降级 mock（带 is_mock=True 与可见提示），不抛错。
"""

import base64
import uuid
from typing import Optional

import httpx

import config
from time_utils import utc_now

ASR_SYSTEM_PROMPT = (
    "You are a highly advanced AI specialized in Automatic Speech Recognition (ASR). "
    "Your sole function is to transcribe the audio provided by the user.\n"
    "Rules:\n"
    "1. Output ONLY the transcribed text.\n"
    "2. No introductory phrases, explanations, or extra text.\n"
    "3. No markdown or formatting.\n"
    "4. If the audio is unclear, inaudible, or contains no speech, output an empty string."
)
ASR_USER_PROMPT = "把这段语音逐字转写成中文（保留原话，口语按听到的写）："

_AUDIO_FORMAT = "wav"


def _extract_audio_bytes(video_path) -> Optional[bytes]:
    """用 ffmpeg 从视频里抽出 16kHz 单声道 WAV，返回字节；无音频轨/失败返回 None。"""
    try:
        import subprocess
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        r = subprocess.run(
            [exe, "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000",
             "-f", "wav", "-"],
            capture_output=True, timeout=120,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout
    except Exception:
        return None
    return None


def _mock(asr_disabled_reason: str) -> dict:
    return {
        "transcript": None,
        "is_mock": True,
        "notice": f"⚠️ 当前语音识别为演示/降级状态（{asr_disabled_reason}），白描暂未引用对话。",
        "asr_run": None,
    }


def _audio_is_silent(wav_bytes: bytes, peak_threshold: int = 150) -> bool:
    """判断 16 位 PCM WAV 是否几乎无声（音量峰值低于阈值）。

    只用于"跳过语音识别"这一降级判断：返回 True 表示基本没声音，不值得调云端 ASR。
    解析失败或格式异常时返回 False（保守：当作有声音，不跳过），避免误伤有对话的视频。
    """
    try:
        if len(wav_bytes) < 44:
            return False
        data_start = wav_bytes.find(b"data")
        if data_start < 0:
            return False
        payload = wav_bytes[data_start + 8:]  # 'data' + 4 字节块长
        try:
            import audioop
            max_amp = audioop.max(payload, 2)  # 16 位 PCM 峰值，C 实现，快
        except Exception:
            # 退化：逐样本取峰值（较慢，仅用于无 audioop 的极端情况）
            max_amp = 0
            for i in range(0, len(payload) - 1, 2):
                val = payload[i] | (payload[i + 1] << 8)
                if val >= 0x8000:
                    val -= 0x10000
                if val < 0:
                    val = -val
                if val > max_amp:
                    max_amp = val
        return max_amp < peak_threshold
    except Exception:
        return False


def transcribe_video(video_path, duration_sec=None) -> dict:
    """对一条视频做语音转写。任何异常都降级为 mock，不抛错。

    降级/跳过规则（为了省掉不必要的云端往返）：
      - ASR_MODE != doubao 或未配置 → mock（未接入）。
      - 短视频（duration_sec < ASR_MIN_DURATION_SEC）→ mock（太短，降级）。
      - 无法抽取音频 / 没有声音轨 → mock。
      - 几乎无声（音量峰值过低）→ mock（跳过）。
    """
    if config.ASR_MODE != "doubao" or not config.ASR_API_KEY:
        return _mock("ASR_MODE=mock，未接入真实语音识别")

    if duration_sec is not None and duration_sec < config.ASR_MIN_DURATION_SEC:
        return _mock(
            f"视频仅 {duration_sec:.0f} 秒，不足 {config.ASR_MIN_DURATION_SEC:.0f} 秒，已降级跳过语音识别",
        )

    wav = _extract_audio_bytes(video_path)
    if not wav:
        return _mock("无法从视频抽取音频，或没有声音轨")

    if _audio_is_silent(wav):
        return _mock("视频几乎无声，已跳过语音识别")

    started_at = utc_now()
    body = {
        "model": config.ASR_MODEL,
        "messages": [
            {"role": "system", "content": ASR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": base64.b64encode(wav).decode("ascii"), "format": _AUDIO_FORMAT},
                    },
                    {"type": "text", "text": ASR_USER_PROMPT},
                ],
            },
        ],
    }
    try:
        resp = httpx.post(
            config.ASR_API_URL,
            headers={
                "Authorization": f"Bearer {config.ASR_API_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=config.ASR_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
        text = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "") or ""
        text = text.strip()
        return {
            "transcript": text or None,
            "is_mock": False,
            "notice": "语音已由豆包识别，白描已引用对话。",
            "asr_run": {
                "provider": "doubao",
                "model": config.ASR_MODEL,
                "status": "completed",
                "started_at": started_at,
                "completed_at": utc_now(),
                "response_raw": payload.get("usage"),
                "request_id": str(uuid.uuid4()),
            },
        }
    except Exception as exc:
        return _mock(f"语音识别调用失败：{exc}")
