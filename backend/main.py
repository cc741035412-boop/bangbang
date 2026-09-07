"""
帮帮师记 API

演示闭环：
  上传素材 → 建观察记录 → 绑定素材 → AI 生成客观白描
  → AI 推荐候选指标 → 教师采纳/否掉/自己加 → 教师补分析和措施 → 定稿 → 查看完整记录
  → 查看 AI 候选采纳率

工作流 A 当前为 mock；工作流 B 可通过配置切换规则 mock 或 DeepSeek。
所有降级输出都带 is_mock=True 和 notice 提示。
"""

from pathlib import Path
from uuid import uuid4
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Optional, List, Dict, Literal
from urllib.parse import quote
import base64
import hashlib
import person_service
import json
import re
import secrets
import shutil
import subprocess
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Header, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_
from sqlmodel import Session, select

from models import (
    engine, Area, ClassRoom, Child, Gender, Teacher,
    Observation, ObservationChild, Media, AIRun, ObservationTag,
    Kindergarten, Account, SMSCode, AuthSession, ExportRecord,
)
from indicators import INDICATORS, all_indicators_flat, level_desc
from config import (
    DEFAULT_CLASSROOM_ID,
    DEFAULT_TEACHER_ID,
    UPLOAD_DIR,
    RUNTIME_ENV,
    SMS_PROVIDER,
    SMS_MOCK_CODE,
    ALLOWED_HOSTS,
)
from time_utils import utc_now
from export_service import (
    DOCX_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    ExportChild,
    ExportIndicator,
    ExportObservation,
    build_observation_document,
    build_observation_pdf,
    child_names,
    kindergarten_datetime,
    KINDERGARTEN_TIMEZONE,
)
import ai_service
import asr_service

app = FastAPI(
    title="帮帮师记 API",
    version="0.2",
    description="幼儿园教师素材沉淀与观察记录生成。工作流 B 支持 mock / DeepSeek 切换。",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith(("/media", "/observations", "/exports", "/metrics")):
        response.headers["Cache-Control"] = "private, no-store"
    return response


@app.exception_handler(RequestValidationError)
async def auth_validation_error(request: Request, exc: RequestValidationError):
    """认证页会直接展示 detail，不向教师暴露 Pydantic 的英文结构错误。"""
    if request.url.path.startswith("/auth/"):
        return JSONResponse(
            status_code=422,
            content={"detail": "填写信息不完整或格式不正确，请检查后重试"},
        )
    return await request_validation_exception_handler(request, exc)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}
EXTENSION_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
}
FALLBACK_CONTENT_TYPES = {"", "application/octet-stream"}
MAX_SIZE = 200 * 1024 * 1024  # 200MB
MAX_DURATION_SEC = 180  # 建议 1~3 分钟；超过会明显降低白描质量，直接拒绝上传
THUMBNAIL_SIZE = 480


# ============================================================
# 请求体定义
# ============================================================

class TagDecision(BaseModel):
    """教师对一条 AI 候选的处理结果"""
    accepted: bool
    reject_reason: Optional[str] = None


class TagCreate(BaseModel):
    """教师自己补一个 AI 没想到的指标"""
    indicator_code: str
    level: int


class ObservationUpdate(BaseModel):
    """教师补观察对象、现场说明，或修改观察记录的四段正文。"""
    model_config = ConfigDict(extra="forbid")

    child_id: Optional[int] = None
    note: Optional[str] = None
    purpose: Optional[str] = None
    narrative: Optional[str] = None
    analysis: Optional[str] = None
    strategy: Optional[str] = None
    location: Optional[str] = None
    background_note: Optional[str] = None


class PersonAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref_indexes: List[int]
    child_id: int


class PeopleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    narrative: str
    assignments: List[PersonAssignment]


class ObservationChildrenUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_ids: List[int]


class ChildUpdate(BaseModel):
    """更新已有幼儿的基础资料；未传入的字段保持不变。"""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[Literal["男", "女"]] = None


class ChildCreate(BaseModel):
    """在当前教师班级新增幼儿。"""
    model_config = ConfigDict(extra="forbid")

    name: str
    classroom_id: Optional[int] = None
    birth_date: Optional[date] = None
    gender: Optional[Literal["male", "female"]] = None


class TeacherUpdate(BaseModel):
    """更新已有教师的姓名；未传入时保持不变。"""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None


class AuthCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str


class AuthLoginRequest(AuthCodeRequest):
    code: str


class AuthRegisterRequest(AuthLoginRequest):
    name: str
    kindergarten_name: str
    classroom_name: str


class AuthPhoneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_phone: str
    code: str


class AuthDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str


class AuthAccountResponse(BaseModel):
    id: int
    phone: str
    teacher_id: int
    name: str
    kindergarten_id: Optional[int] = None
    kindergarten_name: Optional[str] = None
    classroom_id: Optional[int] = None
    classroom_name: Optional[str] = None
    created_at: datetime


class AuthLoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    account: AuthAccountResponse


class NameUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class ClassroomSummaryResponse(BaseModel):
    id: int
    name: str
    child_count: int


class KindergartenTeacherResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str] = None
    classroom_id: Optional[int] = None
    role: Literal["owner", "teacher"]


class KindergartenResponse(BaseModel):
    id: int
    name: str
    classrooms: List[ClassroomSummaryResponse]
    teachers: List[KindergartenTeacherResponse]
    my_role: Literal["owner", "teacher"]


class ObservationCreate(BaseModel):
    """现场新建观察记录；班级、年龄段、素材类型和状态由后端维护。"""
    model_config = ConfigDict(extra="forbid")

    area_id: int
    child_id: Optional[int] = None
    note: Optional[str] = None
    location: Optional[str] = None
    background_note: Optional[str] = None


ObservationStatus = Literal[
    "uploaded",
    "processing",
    "ready_for_review",
    "confirmed",
    "failed",
]


class ObservationResponse(BaseModel):
    """观察记录公开响应；状态与阶段时间戳由后端维护。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    child_id: Optional[int] = None
    area_id: int
    classroom_id: Optional[int] = None
    observer_id: Optional[int] = None
    observed_at: datetime
    age_group: str
    media_type: Optional[str] = None
    location: Optional[str] = None
    background_note: Optional[str] = None
    purpose: Optional[str] = None
    note: Optional[str] = None
    narrative: Optional[str] = None
    analysis: Optional[str] = None
    strategy: Optional[str] = None
    narrative_source: Optional[str] = None
    narrative_ai_raw: Optional[str] = None
    status: ObservationStatus
    created_at: Optional[datetime] = None
    processing_started_at: Optional[datetime] = None
    ready_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None


class ObservationTagResponse(BaseModel):
    """观察指标响应；保留 AI 建议采纳率所需的原始字段。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    observation_id: int
    indicator_code: str
    indicator_name: str
    level: int
    source: str
    accepted: Optional[bool] = None
    confidence: Optional[float] = None
    ai_reason: Optional[str] = None
    rank_in_suggestion: Optional[int] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None


class MediaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stored_filename: str
    content_type: str
    size: int
    duration_sec: Optional[int] = None
    observation_id: Optional[int] = None
    uploaded_at: datetime
    thumbnail_failure_reason: Optional[str] = None


class RelatedChildResponse(BaseModel):
    id: int
    name: str
    classroom_id: int
    birth_date: Optional[date] = None
    gender: Optional[Literal["男", "女"]] = None
    is_primary: bool
    confirmed_observation_count: int = 0


class ChildResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    classroom_id: int
    birth_date: Optional[date] = None
    gender: Optional[Literal["男", "女"]] = None


class ChildProfileRecordResponse(BaseModel):
    observation_id: int
    title: str
    area_name: Optional[str] = None
    observed_at: datetime
    dimensions: List[str]
    exported: bool


class ChildProfileResponse(BaseModel):
    id: int
    name: str
    classroom_id: Optional[int] = None
    classroom_name: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[Literal["male", "female"]] = None
    created_at: Optional[datetime] = None
    media_count: int
    record_count: int
    observed_day_count: int
    dimension_counts: dict[str, int]
    records: List[ChildProfileRecordResponse]


class ExportHistoryResponse(BaseModel):
    id: int
    observation_id: Optional[int] = None
    scope: Literal["single", "monthly"]
    format: Literal["docx", "pdf"]
    file_name: str
    size: int
    child_name: Optional[str] = None
    created_at: datetime
    download_url: Optional[str] = None


class TeacherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    classroom_id: int


class NarrativeGenerationResponse(BaseModel):
    observation_id: int
    status: ObservationStatus
    processing_started_at: datetime
    ready_at: datetime
    narrative: str
    is_mock: bool
    engine: str
    notice: str


class AnalysisSuggestionResponse(BaseModel):
    observation_id: int
    analysis: str
    strategy: str
    is_mock: bool
    engine: str
    notice: str


class ObservationDetailResponse(ObservationResponse):
    observation_mode: Optional[Literal["focused", "explore"]] = None
    narrative_context_changed: bool = False
    suggestions_stale: bool = False
    suggestions_ready: bool = False
    child_name: Optional[str] = None
    classroom_name: Optional[str] = None
    area_name: Optional[str] = None
    child_confirmed_count: int = 0
    children: List[RelatedChildResponse]
    observer: Optional[TeacherResponse] = None
    media: List[MediaResponse]
    tags: List[ObservationTagResponse]

ALLOWED_STATUS_TRANSITIONS = {
    "uploaded": {"processing"},
    "processing": {"ready_for_review", "failed"},
    "ready_for_review": {"confirmed", "processing"},
    "confirmed": {"ready_for_review"},
    "failed": {"processing"},
}


def ensure_status_transition(obs: Observation, target_status: str):
    """非法流转统一返回当前状态和目标状态。"""
    allowed_targets = ALLOWED_STATUS_TRANSITIONS.get(obs.status, set())
    if target_status not in allowed_targets:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"不允许从 {obs.status} 流转到 {target_status}",
                "current_status": obs.status,
                "target_status": target_status,
            },
        )


def transition_observation(
    obs: Observation,
    target_status: str,
    *,
    failure_reason: Optional[str] = None,
):
    """执行合法状态流转并记录对应阶段时间戳。"""
    ensure_status_transition(obs, target_status)
    now = utc_now()
    obs.status = target_status

    if target_status == "processing":
        obs.processing_started_at = now
        obs.failure_reason = None
    elif target_status == "ready_for_review":
        obs.ready_at = now
        obs.failure_reason = None
    elif target_status == "confirmed":
        obs.confirmed_at = now
    elif target_status == "failed":
        obs.failure_reason = failure_reason or "AI 处理失败"


def sync_primary_child(session: Session, observation_id: int, child_id: Optional[int]):
    """让兼容字段 child_id 与多人关联表中的主观察对象保持一致。"""
    primary_links = session.exec(
        select(ObservationChild).where(
            ObservationChild.observation_id == observation_id,
            ObservationChild.is_primary == True,  # noqa: E712
        )
    ).all()
    for link in primary_links:
        if child_id is None or link.child_id != child_id:
            session.delete(link)

    if child_id is None:
        return
    link = session.get(ObservationChild, (observation_id, child_id))
    if link:
        link.is_primary = True
    else:
        link = ObservationChild(
            observation_id=observation_id,
            child_id=child_id,
            is_primary=True,
        )
    session.add(link)


def classroom_child_names_for_anonymization(
    session: Session,
    observation: Observation,
) -> List[str]:
    """主观察对象优先，其余班级幼儿按 id 排序，供工作流 B 脱敏。"""
    if observation.classroom_id is None:
        return []
    primary_ids = set(session.exec(
        select(ObservationChild.child_id).where(
            ObservationChild.observation_id == observation.id,
            ObservationChild.is_primary == True,  # noqa: E712
        )
    ).all())
    children = session.exec(
        select(Child)
        .where(Child.classroom_id == observation.classroom_id)
        .order_by(Child.id)
    ).all()
    selected_ids = set(session.exec(select(ObservationChild.child_id).where(
        ObservationChild.observation_id == observation.id
    )).all())
    children.sort(key=lambda child: (child.id not in primary_ids, child.id not in selected_ids, child.id))
    return [child.name for child in children]


def confirmed_observation_count(session: Session, child_id: int) -> int:
    """多人记录会分别计入每个关联幼儿的成长档案。"""
    return session.exec(
        select(func.count(ObservationChild.observation_id)).join(
            Observation,
            Observation.id == ObservationChild.observation_id,
        ).where(
            ObservationChild.child_id == child_id,
            Observation.status == "confirmed",
        )
    ).one()


def resolve_upload_type(file: UploadFile):
    """优先信任明确 MIME；仅在 MIME 缺失或通用二进制时按扩展名回退。"""
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type in ALLOWED_TYPES:
        return content_type, ALLOWED_TYPES[content_type]

    suffix = Path(file.filename or "").suffix.lower()
    if content_type in FALLBACK_CONTENT_TYPES and suffix in EXTENSION_TYPES:
        return EXTENSION_TYPES[suffix], suffix

    raise HTTPException(400, "只支持照片和视频（JPG、PNG、HEIC、MP4、MOV）")


def get_thumbnail_path(stored_filename: str) -> Path:
    return UPLOAD_DIR / f"{stored_filename}.thumbnail.png"


def _frame_is_blank(data_uri: str) -> bool:
    """判断一帧是否是无内容帧（近乎纯黑 / 纯白 / 几乎没有纹理）。

    用 Pillow 解码成灰度、缩到小尺寸后统计均值与标准差：
      - 标准差极小（画面几乎无变化，如纯色/纯黑/纯白）→ 空白；
      - 极暗或极亮且纹理很少 → 空白。
    Pillow 不可用时返回 False（宁可多保留一帧，也不误删真实画面）。
    """
    try:
        from PIL import Image
        raw = base64.b64decode(data_uri.split(",", 1)[1])
        img = Image.open(BytesIO(raw)).convert("L")
        img.thumbnail((64, 64))
        hist = img.histogram()
        total = sum(hist)
        if total == 0:
            return False
        mean = sum(i * hist[i] for i in range(256)) / total
        if total > 1:
            variance = sum(hist[i] * (i - mean) ** 2 for i in range(256)) / (total - 1)
        else:
            variance = 0.0
        std = variance ** 0.5
        if std < 10:
            return True
        if (mean < 15 or mean > 240) and std < 30:
            return True
        return False
    except Exception:
        return False


def _blank_fallback_offsets(t: float, duration: float, max_search: int = 8) -> List[float]:
    """空白帧的候选重采样偏移（秒），朝素材"有内容的方向"扫并回到边界内。"""
    offsets: List[float] = []
    if t <= 0.1:  # 开头空白 → 往后找
        offsets = [float(i) for i in range(1, max_search + 1)]
    elif t >= duration - 0.2:  # 结尾空白 → 往前找
        offsets = [-float(i) for i in range(1, max_search + 1)]
    else:  # 中间空白 → 先往后再往前
        for i in range(1, max_search + 1):
            offsets.append(float(i))
            offsets.append(-float(i))
    return offsets[:max_search]


def _grab_frame(exe: str, source: Path, t: float, duration: float) -> Optional[str]:
    """在时间点 t 抽 1 帧 PNG，返回 data_uri；失败返回 None。时间自动钳制在素材范围内。"""
    tt = max(0.0, min(t, max(0.0, duration - 0.05)))
    r = subprocess.run(
        [exe, "-y", "-ss", str(tt), "-i", str(source),
         "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-"],
        capture_output=True, timeout=60,
    )
    if r.returncode == 0 and r.stdout:
        return "data:image/png;base64," + base64.b64encode(r.stdout).decode("ascii")
    return None


def _probe_video_duration(path: Path) -> Optional[float]:
    """用 ffmpeg 探测视频时长（秒）；失败返回 None。"""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        probe = subprocess.run(
            [exe, "-i", str(path)], capture_output=True, text=True, timeout=30
        )
        for line in probe.stderr.splitlines():
            if "Duration:" in line:
                m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", line)
                if m:
                    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        return None
    return None


def suggested_frame_count(duration_sec: Optional[float]) -> int:
    """按视频时长决定抽帧数量（与产品 1~3 分钟片段上限对齐）。

    背景：短视频（如 8 秒）抽固定 10 帧几乎每一秒一帧，信息大量重复；
    而 2~3 分钟视频统一 10 帧则帧间接近 9~18 秒，模型看到的是离散快照，
    写出来的白描容易变成"第 X 秒时…"的刻板罗列，缺少来龙去脉。
    因此按时长分档，长视频**加密度**（帧间 5~8 秒），以便白描连贯：
      ≤10s   → 4 帧（3~5）
      ≤30s   → 6 帧（5~8）
      ≤60s   → 10 帧（8~12）
      60~120s → 16 帧
      120~180s → 20 帧（封顶，配合 3 分钟上限）。
    更长的视频留待后续按内容/场景变化抽帧（分段 + 场景检测）。
    """
    if duration_sec is None or duration_sec <= 0:
        return 10
    if duration_sec <= 10:
        return 4
    if duration_sec <= 30:
        return 6
    if duration_sec <= 60:
        return 10
    if duration_sec <= 120:
        return 16
    return 20


def _extract_frames_in_one_pass(exe: str, source: Path, count: int, duration: float) -> List[bytes]:
    """用**一次** ffmpeg 进程，按 fps=count/duration 均匀抽出 count 帧 PNG 字节。

    相比"每帧一次子进程"，把子进程开销从 N 次压到 1 次（外加空白帧的少量定向重采样）。
    输出到临时目录再读回，避免解析连续 PNG 二进制流；失败返回空列表。
    """
    try:
        fps = count / duration if duration > 0 else 1
        with tempfile.TemporaryDirectory(prefix="frames-") as tmp:
            pattern = str(Path(tmp) / "f-%04d.png")
            subprocess.run(
                [exe, "-y", "-i", str(source), "-vf", f"fps={fps:.6f}",
                 "-frames:v", str(count), str(pattern)],
                capture_output=True, timeout=60, check=False,
            )
            files = sorted(Path(tmp).glob("f-*.png"))
            frames: List[bytes] = []
            for f in files[:count]:
                try:
                    frames.append(f.read_bytes())
                except OSError:
                    continue
            return frames
    except Exception:
        return []


def _content_change_timestamps(exe: str, source: Path, duration: float, count: int) -> List[float]:
    """基于相邻帧的下采样灰度签名差异，找出"内容变化最大"的时刻（scene-aware）。

    用**一次** ffmpeg 进程抽取下采样灰度帧（scale=16x16, gray），再比较相邻帧差异
    （像素变化比例），差异越大说明此处内容/动作变化越明显。返回按时间升序的时刻列表。
    """
    try:
        steps = max(40, min(int(duration) * 2, 120))
        fps = steps / duration if duration > 0 else 1
        with tempfile.TemporaryDirectory(prefix="chg-") as tmp:
            raw = str(Path(tmp) / "sig.raw")
            subprocess.run(
                [exe, "-y", "-i", str(source), "-vf",
                 f"fps={fps:.6f},scale=16:16,format=gray",
                 "-f", "rawvideo", "-pix_fmt", "gray", raw],
                capture_output=True, timeout=60, check=False,
            )
            data = Path(raw).read_bytes()
        sig_len = 16 * 16
        chunks = [data[i:i + sig_len] for i in range(0, len(data) - sig_len + 1, sig_len)]
        if len(chunks) < 3:
            return []
        scored: List[tuple] = []
        for i in range(len(chunks) - 1):
            a, b = chunks[i], chunks[i + 1]
            diff = sum(1 for x, y in zip(a, b) if x != y) / sig_len
            if diff <= 0.02:
                continue
            scored.append((diff, (i + 0.5) / steps * duration))
        scored.sort(key=lambda x: x[0], reverse=True)
        spacing = duration / max(count, 1)
        picked: List[float] = []
        for _score, ts in scored:
            if all(abs(ts - p) >= spacing for p in picked):
                picked.append(ts)
            if len(picked) >= max(2, count - 2):
                break
        return sorted(picked)
    except Exception:
        return []


def _select_timestamps(duration: float, count: int, change_ts: List[float]) -> List[float]:
    """合成最终抽帧时刻：优先内容变化点，再用均匀点补足到 count，并保留首尾。"""
    ts: List[float] = [0.0, max(0.0, duration - 0.1)]
    spacing = duration / max(count, 1)
    for t in sorted(change_ts):
        if all(abs(t - x) >= spacing for x in ts):
            ts.append(t)
        if len(ts) >= count:
            break
    if len(ts) < count and count > 1:
        even = [duration * i / count for i in range(count)]
        for t in even:
            if all(abs(t - x) >= spacing for x in ts):
                ts.append(t)
            if len(ts) >= count:
                break
    return sorted(ts)[:count]


def _finalize_frames(timestamps: List[float], frame_uris: List[Optional[str]], exe: str, source: Path, duration: float) -> List[Dict]:
    """对一组 (时刻, data_uri) 做空白帧重采样 + 排序，返回最终帧列表。"""
    frames: List[Dict] = []
    for t, data_uri in zip(timestamps, frame_uris):
        if data_uri is None:
            continue
        if _frame_is_blank(data_uri):
            # 该时间点是空白帧 → 在附近重采样，取一帧有内容的
            replaced = False
            for delta in _blank_fallback_offsets(t, duration):
                alt = _grab_frame(exe, source, t + delta, duration)
                if alt is not None and not _frame_is_blank(alt):
                    frames.append({"timestamp_sec": round(t + delta, 1), "data_uri": alt})
                    replaced = True
                    break
            if not replaced:
                # 实在找不到有内容的帧 → 保留原帧，交给提示词"跳过不写"
                frames.append({"timestamp_sec": round(t, 1), "data_uri": data_uri})
        else:
            frames.append({"timestamp_sec": round(t, 1), "data_uri": data_uri})
    frames.sort(key=lambda f: f["timestamp_sec"])
    return frames


def _frames_from_timestamps(exe: str, source: Path, timestamps: List[float], duration: float) -> List[Dict]:
    """按给定时刻逐帧抽取（内容变化点）并做空白帧处理。"""
    uris = [_grab_frame(exe, source, t, duration) for t in timestamps]
    return _finalize_frames(timestamps, uris, exe, source, duration)


def _even_frames(exe: str, source: Path, duration: float, count: int) -> List[Dict]:
    """均匀抽帧：一次 ffmpeg 进程输出 count 帧，再做空白帧处理。"""
    frame_datas = _extract_frames_in_one_pass(exe, source, count, duration)
    if not frame_datas:
        return []
    timestamps = [duration * i / count for i in range(count)] if count > 1 else [0.0]
    uris = ["data:image/png;base64," + base64.b64encode(data).decode("ascii") for data in frame_datas]
    return _finalize_frames(timestamps, uris, exe, source, duration)


def _extract_video_frames(source: Path, count: Optional[int] = None) -> List[Dict]:
    """按"内容/场景变化"抽关键帧，返回 [{timestamp_sec, data_uri}]。

    依赖 imageio-ffmpeg（pip 自带 ffmpeg 二进制，无需系统安装）。
    - count 缺省时按视频时长自适应（见 suggested_frame_count）；显式传入则按给定值。
    - 先用一次 ffmpeg 进程抽下采样灰度签名，找出相邻帧变化最大的时刻（scene-aware）；
      抽帧时刻定为"内容变化点 + 均匀补足 + 首尾"，让白描更有来龙去脉。
    - 无内容变化（连续镜头/失败）时回到一次进程的均匀抽帧；
    - 空白帧在附近定向重采样；抽帧失败或不是合法视频时返回空列表（调用方降级到 mock）。
    """
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return []

    try:
        duration = _probe_video_duration(source)
        if not duration or duration <= 0:
            return []

        if count is None:
            count = suggested_frame_count(duration)
        count = max(1, int(count))

        change_ts = _content_change_timestamps(exe, source, duration, count)
        if len(change_ts) >= 2:
            timestamps = _select_timestamps(duration, count, change_ts)
            frames = _frames_from_timestamps(exe, source, timestamps, duration)
            return frames if frames else _even_frames(exe, source, duration, count)

        # 无明显内容变化（连续镜头/失败）→ 均匀抽帧
        return _even_frames(exe, source, duration, count)
    except Exception:
        return []


def extract_highlight_frames(source: Path, max_frames: int = 3) -> List[bytes]:
    """从视频里挑几个"内容变化最大"的时刻，抽若干帧 PNG 作为「精彩瞬间」静态图。

    用于导出观察记录时，在开头放几张代表性的画面（家长友好）。返回 PNG 列表；
    无可用画面或图片无效时返回空列表（调用方跳过插入）。"""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return []
    try:
        duration = _probe_video_duration(source)
        if not duration or duration <= 0:
            return []
        change_ts = _content_change_timestamps(exe, source, duration, max(16, 20))
        if not change_ts:
            change_ts = [duration * 0.5]
        # 均匀挑 max_frames 个变化时刻，让照片覆盖整段，而不是都挤在开头
        if max_frames > 1 and len(change_ts) > 1:
            idxs = sorted(set(round(i * (len(change_ts) - 1) / (max_frames - 1)) for i in range(max_frames)))
            pick_ts = [change_ts[i] for i in idxs]
        else:
            pick_ts = change_ts[:max_frames]
        frames = []
        for ts in pick_ts:
            result = subprocess.run(
                [exe, "-y", "-ss", str(ts), "-i", str(source), "-frames:v", "1",
                 "-vf", "scale='min(640,iw)':-2", "-f", "image2pipe", "-c:v", "png", "-"],
                capture_output=True, timeout=30, check=False,
            )
            if result.returncode == 0 and result.stdout:
                try:
                    from PIL import Image
                    Image.open(BytesIO(result.stdout)).verify()
                except Exception:
                    continue
                frames.append(result.stdout)
        return frames
    except Exception:
        return []


def prepare_export_photo(source: Path) -> Optional[bytes]:
    """把上传照片转成 DOCX/PDF 都能稳定读取的 JPEG，并校正手机拍摄方向。"""
    try:
        if source.suffix.lower() in {".heic", ".heif"}:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        from PIL import Image, ImageOps

        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode != "RGB":
                image = image.convert("RGB")
            image.thumbnail((1800, 1800))
            output = BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
            return output.getvalue()
    except (ImportError, OSError, ValueError):
        return None


def _media_vision_frames(media: Media) -> Optional[List[Dict]]:
    """把素材转成"视觉模型可用的画面帧列表"，供豆包白描使用。

    - 图片：用原图（1 帧）。
    - 视频：用 ffmpeg 按时间均匀抽帧（帧数按视频时长自适应，见 suggested_frame_count），按时间顺序给模型。
    返回 None 表示没有任何可用画面（调用方降级到 mock）。
    每个元素形如 {"timestamp_sec": float|None, "data_uri": "data:image/...;base64,xxx"}。
    """
    if media.content_type.startswith("image/"):
        path = UPLOAD_DIR / media.stored_filename
        if not path.is_file():
            return None
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        return [{
            "timestamp_sec": None,
            "data_uri": f"data:{media.content_type};base64,{base64.b64encode(raw).decode('ascii')}",
        }]

    source = UPLOAD_DIR / media.stored_filename
    if not source.is_file():
        return None
    frames = _extract_video_frames(source)
    return frames or None


def get_thumbnail_error_path(stored_filename: str) -> Path:
    return UPLOAD_DIR / f"{stored_filename}.thumbnail-error.txt"


def get_thumbnail_failure_reason(stored_filename: str) -> Optional[str]:
    if get_thumbnail_path(stored_filename).is_file():
        return None
    error_path = get_thumbnail_error_path(stored_filename)
    if not error_path.is_file():
        return None
    return error_path.read_text(encoding="utf-8").strip() or "视频缩略图生成失败"


def generate_video_thumbnail(source_path: Path) -> Optional[str]:
    """使用 imageio-ffmpeg 生成跨平台视频缩略图；失败不影响素材保存。"""
    thumbnail_path = get_thumbnail_path(source_path.name)
    error_path = get_thumbnail_error_path(source_path.name)
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        reason = "服务器视频处理组件不可用"
        error_path.write_text(reason, encoding="utf-8")
        return reason

    try:
        with tempfile.TemporaryDirectory(prefix="thumbnail-", dir=UPLOAD_DIR) as temp_dir:
            generated_path = Path(temp_dir) / "thumbnail.png"
            result = subprocess.run(
                [
                    exe,
                    "-y",
                    "-ss",
                    "0.1",
                    "-i",
                    str(source_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale='min({THUMBNAIL_SIZE},iw)':-2",
                    str(generated_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0 or not generated_path.is_file():
                reason = "当前视频编码暂时无法生成缩略图"
                error_path.write_text(reason, encoding="utf-8")
                return reason
            generated_path.replace(thumbnail_path)
    except subprocess.TimeoutExpired:
        reason = "视频缩略图生成超时"
        error_path.write_text(reason, encoding="utf-8")
        return reason
    except OSError:
        reason = "视频缩略图生成失败"
        error_path.write_text(reason, encoding="utf-8")
        return reason

    error_path.unlink(missing_ok=True)
    return None


def media_response(media: Media):
    data = media.model_dump()
    data["thumbnail_failure_reason"] = get_thumbnail_failure_reason(media.stored_filename)
    return data


# ============================================================
# 账号与认证
# ============================================================

AUTH_COOKIE_NAME = "bangbang_access_token"
AUTH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
SMS_CODE_TTL_SECONDS = 5 * 60
SMS_COOLDOWN_SECONDS = 60
PRODUCTION_ENVS = {"production", "prod"}
SECURE_COOKIE_ENVS = PRODUCTION_ENVS | {"demo"}


def validate_phone(phone: str) -> str:
    normalized = phone.strip()
    if not re.fullmatch(r"1\d{10}", normalized):
        raise HTTPException(422, "请输入正确的 11 位手机号")
    return normalized


def validate_code(code: str) -> str:
    normalized = code.strip()
    if not re.fullmatch(r"\d{6}", normalized):
        raise HTTPException(422, "请输入 6 位数字验证码")
    return normalized


def required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(422, f"请填写{label}")
    return normalized


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def request_access_token(request: Request, authorization: Optional[str]) -> Optional[str]:
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() != "bearer" or not value.strip():
            raise HTTPException(401, "登录状态无效，请重新登录")
        return value.strip()
    return request.cookies.get(AUTH_COOKIE_NAME)


def authenticated_account(
    session: Session,
    request: Request,
    authorization: Optional[str],
    *,
    required: bool = True,
):
    token = request_access_token(request, authorization)
    if not token:
        if required:
            raise HTTPException(401, "请先登录")
        return None

    auth_session = session.exec(
        select(AuthSession).where(AuthSession.token_hash == token_hash(token))
    ).first()
    now = utc_now()
    if (
        not auth_session
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= now
    ):
        if required:
            raise HTTPException(401, "登录已失效，请重新登录")
        # 可选鉴权（required=False）：token 过期/失效按匿名处理，
        # 避免因浏览器残留的旧 token 把整页查询打成 401（如今日素材页）。
        return None
    account = session.get(Account, auth_session.account_id)
    if not account or account.deleted_at is not None:
        if required:
            raise HTTPException(401, "账号已注销或登录已失效")
        return None
    return account, auth_session


def authenticated_teacher(
    session: Session,
    request: Request,
    authorization: Optional[str],
):
    """返回当前账号与教师，并校验账号、教师、班级、园所链路一致。"""
    account, _ = authenticated_account(session, request, authorization)
    teacher = session.get(Teacher, account.teacher_id)
    room = session.get(ClassRoom, teacher.classroom_id) if teacher else None
    if not teacher or not room or room.kindergarten_id != account.kindergarten_id:
        raise HTTPException(401, "账号归属信息无效，请联系管理员")
    return account, teacher


def owned_observation(session: Session, teacher: Teacher, observation_id: int) -> Observation:
    """只返回当前教师创建且属于当前班级的记录，避免用 id 枚举他人数据。"""
    observation = session.get(Observation, observation_id)
    if (
        not observation
        or observation.observer_id != teacher.id
        or observation.classroom_id != teacher.classroom_id
    ):
        raise HTTPException(404, "观察记录不存在")
    return observation


def owned_media(session: Session, teacher: Teacher, media_id: int) -> Media:
    """素材必须已经绑定到当前教师拥有的观察记录。"""
    media = session.get(Media, media_id)
    if not media or media.observation_id is None:
        raise HTTPException(404, "素材不存在")
    owned_observation(session, teacher, media.observation_id)
    return media


def account_response(session: Session, account: Account) -> AuthAccountResponse:
    teacher = session.get(Teacher, account.teacher_id)
    kindergarten = session.get(Kindergarten, account.kindergarten_id)
    room = session.get(ClassRoom, teacher.classroom_id) if teacher else None
    if not teacher:
        raise HTTPException(500, "账号关联的教师信息不存在")
    return AuthAccountResponse(
        id=account.id,
        phone=account.phone,
        teacher_id=teacher.id,
        name=teacher.name,
        kindergarten_id=kindergarten.id if kindergarten else None,
        kindergarten_name=kindergarten.name if kindergarten else None,
        classroom_id=room.id if room else None,
        classroom_name=room.name if room else None,
        created_at=account.created_at,
    )


def issue_session(session: Session, account: Account):
    raw_token = secrets.token_urlsafe(32)
    session.add(AuthSession(
        account_id=account.id,
        token_hash=token_hash(raw_token),
        expires_at=utc_now() + timedelta(seconds=AUTH_TOKEN_TTL_SECONDS),
    ))
    return raw_token


def set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=AUTH_TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=RUNTIME_ENV in SECURE_COOKIE_ENVS,
        path="/",
    )


def sms_value() -> str:
    if SMS_PROVIDER == "mock":
        if RUNTIME_ENV in PRODUCTION_ENVS:
            raise HTTPException(503, "生产环境短信服务尚未配置，请联系管理员")
        if not re.fullmatch(r"\d{6}", SMS_MOCK_CODE):
            raise HTTPException(503, "本地验证码配置无效，请联系管理员")
        return SMS_MOCK_CODE
    raise HTTPException(503, "短信服务尚未配置，请联系管理员")


def infer_sms_purpose(
    session: Session,
    phone: str,
    authenticated: Optional[tuple],
) -> str:
    existing = session.exec(select(Account).where(Account.phone == phone)).first()
    if authenticated:
        account, _ = authenticated
        return "delete_account" if phone == account.phone else "change_phone"
    if existing and existing.deleted_at is not None:
        raise HTTPException(410, "该手机号对应的账号已注销，暂时不能重新注册")
    return "login" if existing else "register"


def consume_sms_code(session: Session, phone: str, code: str, purpose: str):
    now = utc_now()
    sms = session.exec(
        select(SMSCode)
        .where(
            SMSCode.phone == phone,
            SMSCode.code == code,
            SMSCode.purpose == purpose,
            SMSCode.consumed_at == None,  # noqa: E711
        )
        .order_by(SMSCode.created_at.desc())
    ).first()
    if not sms or sms.expires_at <= now:
        raise HTTPException(400, "验证码不正确或已失效，请重新获取")
    sms.consumed_at = now
    session.add(sms)


def inferred_age_group(classroom_name: str) -> str:
    if "小" in classroom_name:
        return "small"
    if "大" in classroom_name:
        return "large"
    return "middle"


def require_owner(account: Account):
    if account.role != "owner":
        raise HTTPException(403, "只有园所管理员可以进行这项操作")


def masked_phone(phone: str) -> str:
    return f"{phone[:3]}****{phone[-4:]}"


def current_kindergarten_response(
    session: Session,
    account: Account,
) -> KindergartenResponse:
    kindergarten = session.get(Kindergarten, account.kindergarten_id)
    if not kindergarten:
        raise HTTPException(404, "当前账号没有关联园所")
    rooms = session.exec(
        select(ClassRoom)
        .where(ClassRoom.kindergarten_id == kindergarten.id)
        .order_by(ClassRoom.id)
    ).all()
    classroom_rows = []
    for room in rooms:
        child_count = session.exec(
            select(func.count(Child.id)).where(Child.classroom_id == room.id)
        ).one()
        classroom_rows.append(ClassroomSummaryResponse(
            id=room.id,
            name=room.name,
            child_count=child_count,
        ))

    accounts = session.exec(
        select(Account)
        .where(
            Account.kindergarten_id == kindergarten.id,
            Account.deleted_at == None,  # noqa: E711
        )
        .order_by(Account.id)
    ).all()
    teacher_rows = []
    for item in accounts:
        teacher = session.get(Teacher, item.teacher_id)
        if teacher:
            teacher_rows.append(KindergartenTeacherResponse(
                id=teacher.id,
                name=teacher.name,
                phone=masked_phone(item.phone),
                classroom_id=teacher.classroom_id,
                role="owner" if item.role == "owner" else "teacher",
            ))
    return KindergartenResponse(
        id=kindergarten.id,
        name=kindergarten.name,
        classrooms=classroom_rows,
        teachers=teacher_rows,
        my_role="owner" if account.role == "owner" else "teacher",
    )


@app.post("/auth/code", tags=["账号与认证"])
def send_auth_code(
    payload: AuthCodeRequest,
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None),
):
    phone = validate_phone(payload.phone)
    with Session(engine) as session:
        try:
            authenticated = authenticated_account(
                session, request, authorization, required=False,
            )
        except HTTPException as exc:
            if exc.status_code != 401:
                raise
            # 登录/注册页可能还带着上一个临时库或已退出会话的旧 token。
            # 获取验证码本来就是匿名入口，旧登录态不能把新登录或注册卡死。
            authenticated = None
            response.delete_cookie(AUTH_COOKIE_NAME, path="/")
        purpose = infer_sms_purpose(session, phone, authenticated)
        now = utc_now()
        latest = session.exec(
            select(SMSCode)
            .where(SMSCode.phone == phone)
            .order_by(SMSCode.created_at.desc())
        ).first()
        if latest and (now - latest.created_at).total_seconds() < SMS_COOLDOWN_SECONDS:
            raise HTTPException(429, "验证码发送太频繁，请稍后再试")
        code = sms_value()
        session.add(SMSCode(
            phone=phone,
            code=code,
            purpose=purpose,
            expires_at=now + timedelta(seconds=SMS_CODE_TTL_SECONDS),
        ))
        session.commit()
    return {"expires_in": SMS_CODE_TTL_SECONDS, "cooldown_sec": SMS_COOLDOWN_SECONDS}


@app.post("/auth/login", response_model=AuthLoginResponse, tags=["账号与认证"])
def login(
    payload: AuthLoginRequest,
    response: Response,
):
    phone = validate_phone(payload.phone)
    code = validate_code(payload.code)
    with Session(engine) as session:
        account = session.exec(
            select(Account).where(Account.phone == phone, Account.deleted_at == None)  # noqa: E711
        ).first()
        if not account:
            raise HTTPException(404, "这个手机号还没有注册，请先注册")
        consume_sms_code(session, phone, code, "login")
        token = issue_session(session, account)
        result = AuthLoginResponse(
            access_token=token,
            expires_in=AUTH_TOKEN_TTL_SECONDS,
            account=account_response(session, account),
        )
        session.commit()
    set_auth_cookie(response, token)
    return result


@app.post("/auth/register", response_model=AuthLoginResponse, tags=["账号与认证"])
def register(
    payload: AuthRegisterRequest,
    response: Response,
):
    phone = validate_phone(payload.phone)
    code = validate_code(payload.code)
    name = required_text(payload.name, "姓名")
    kindergarten_name = required_text(payload.kindergarten_name, "所在园所")
    classroom_name = required_text(payload.classroom_name, "带班班级")
    with Session(engine) as session:
        if session.exec(select(Account).where(Account.phone == phone)).first():
            raise HTTPException(409, "这个手机号已经注册，请直接登录")
        consume_sms_code(session, phone, code, "register")
        kindergarten = Kindergarten(name=kindergarten_name)
        session.add(kindergarten)
        session.flush()
        room = ClassRoom(
            name=classroom_name,
            age_group=inferred_age_group(classroom_name),
            kindergarten_id=kindergarten.id,
        )
        session.add(room)
        session.flush()
        teacher = Teacher(name=name, classroom_id=room.id)
        session.add(teacher)
        session.flush()
        account = Account(
            phone=phone,
            teacher_id=teacher.id,
            kindergarten_id=kindergarten.id,
            role="owner",
        )
        session.add(account)
        session.flush()
        token = issue_session(session, account)
        result = AuthLoginResponse(
            access_token=token,
            expires_in=AUTH_TOKEN_TTL_SECONDS,
            account=account_response(session, account),
        )
        session.commit()
    set_auth_cookie(response, token)
    return result


@app.get("/auth/me", response_model=AuthAccountResponse, tags=["账号与认证"])
def auth_me(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        return account_response(session, account)


@app.post("/auth/logout", status_code=204, tags=["账号与认证"])
def logout(
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None),
):
    with Session(engine) as session:
        _, auth_session = authenticated_account(session, request, authorization)
        auth_session.revoked_at = utc_now()
        session.add(auth_session)
        session.commit()
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@app.patch("/auth/phone", response_model=AuthAccountResponse, tags=["账号与认证"])
def change_phone(
    payload: AuthPhoneRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    new_phone = validate_phone(payload.new_phone)
    code = validate_code(payload.code)
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        if new_phone == account.phone:
            raise HTTPException(409, "新手机号不能和当前手机号相同")
        if session.exec(select(Account).where(Account.phone == new_phone)).first():
            raise HTTPException(409, "这个手机号已经被其他账号使用")
        consume_sms_code(session, new_phone, code, "change_phone")
        account.phone = new_phone
        session.add(account)
        session.commit()
        session.refresh(account)
        return account_response(session, account)


def stage_account_media(session: Session, observation_ids: List[int]):
    media_rows = []
    if observation_ids:
        media_rows = session.exec(
            select(Media).where(Media.observation_id.in_(observation_ids))
        ).all()
    staging = Path(tempfile.mkdtemp(prefix="account-delete-", dir=UPLOAD_DIR))
    moved = []
    try:
        for media in media_rows:
            candidates = [
                UPLOAD_DIR / media.stored_filename,
                get_thumbnail_path(media.stored_filename),
                get_thumbnail_error_path(media.stored_filename),
            ]
            for source in candidates:
                if source.is_file():
                    target = staging / source.name
                    source.replace(target)
                    moved.append((source, target))
    except Exception:
        for source, target in reversed(moved):
            if target.exists():
                target.replace(source)
        shutil.rmtree(staging, ignore_errors=True)
        raise HTTPException(500, "素材文件暂时无法安全删除，请稍后重试")
    return staging, moved, media_rows


@app.delete("/auth/account", status_code=204, tags=["账号与认证"])
def delete_account(
    payload: AuthDeleteRequest,
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None),
):
    code = validate_code(payload.code)
    staging = None
    moved = []
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        consume_sms_code(session, account.phone, code, "delete_account")
        observations = session.exec(
            select(Observation).where(Observation.observer_id == account.teacher_id)
        ).all()
        observation_ids = [item.id for item in observations]
        staging, moved, media_rows = stage_account_media(session, observation_ids)
        try:
            if observation_ids:
                for tag in session.exec(select(ObservationTag).where(ObservationTag.observation_id.in_(observation_ids))).all():
                    session.delete(tag)
                for run in session.exec(select(AIRun).where(AIRun.observation_id.in_(observation_ids))).all():
                    session.delete(run)
                for link in session.exec(select(ObservationChild).where(ObservationChild.observation_id.in_(observation_ids))).all():
                    session.delete(link)
            for media in media_rows:
                session.delete(media)
            for observation in observations:
                session.delete(observation)
            for auth_session in session.exec(select(AuthSession).where(AuthSession.account_id == account.id)).all():
                auth_session.revoked_at = utc_now()
                session.add(auth_session)
            account.deleted_at = utc_now()
            session.add(account)
            session.commit()
        except Exception:
            session.rollback()
            for source, target in reversed(moved):
                if target.exists():
                    target.replace(source)
            if staging:
                shutil.rmtree(staging, ignore_errors=True)
            raise HTTPException(500, "账号注销没有完成，数据未删除，请稍后重试")
    if staging:
        shutil.rmtree(staging, ignore_errors=True)
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    response.status_code = 204
    return response


# ============================================================
# 基础
# ============================================================

@app.get("/health", tags=["基础"])
def health():
    return {"status": "ok"}


@app.get(
    "/kindergartens/current",
    response_model=KindergartenResponse,
    tags=["园所与班级"],
)
def get_current_kindergarten(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        return current_kindergarten_response(session, account)


@app.patch(
    "/kindergartens/current",
    response_model=KindergartenResponse,
    tags=["园所与班级"],
)
def rename_current_kindergarten(
    payload: NameUpdate,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    name = required_text(payload.name, "园所名称")
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        require_owner(account)
        kindergarten = session.get(Kindergarten, account.kindergarten_id)
        if not kindergarten:
            raise HTTPException(404, "当前账号没有关联园所")
        kindergarten.name = name
        session.add(kindergarten)
        session.commit()
        return current_kindergarten_response(session, account)


@app.post(
    "/classrooms",
    response_model=ClassroomSummaryResponse,
    status_code=201,
    tags=["园所与班级"],
)
def create_classroom(
    payload: NameUpdate,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    name = required_text(payload.name, "班级名称")
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        require_owner(account)
        room = ClassRoom(
            name=name,
            age_group=inferred_age_group(name),
            kindergarten_id=account.kindergarten_id,
        )
        session.add(room)
        session.commit()
        session.refresh(room)
        return ClassroomSummaryResponse(id=room.id, name=room.name, child_count=0)


def owned_classroom(session: Session, account: Account, classroom_id: int) -> ClassRoom:
    room = session.get(ClassRoom, classroom_id)
    if not room or room.kindergarten_id != account.kindergarten_id:
        raise HTTPException(404, "班级不存在")
    return room


@app.patch(
    "/classrooms/{classroom_id}",
    response_model=ClassroomSummaryResponse,
    tags=["园所与班级"],
)
def rename_classroom(
    classroom_id: int,
    payload: NameUpdate,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    name = required_text(payload.name, "班级名称")
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        require_owner(account)
        room = owned_classroom(session, account, classroom_id)
        room.name = name
        room.age_group = inferred_age_group(name)
        session.add(room)
        child_count = session.exec(
            select(func.count(Child.id)).where(Child.classroom_id == room.id)
        ).one()
        session.commit()
        return ClassroomSummaryResponse(
            id=room.id,
            name=room.name,
            child_count=child_count,
        )


@app.delete("/classrooms/{classroom_id}", status_code=204, tags=["园所与班级"])
def delete_classroom(
    classroom_id: int,
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None),
):
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        require_owner(account)
        room = owned_classroom(session, account, classroom_id)
        child_count = session.exec(
            select(func.count(Child.id)).where(Child.classroom_id == room.id)
        ).one()
        if child_count:
            raise HTTPException(
                409,
                f"{room.name}还有 {child_count} 名幼儿，请先移出或删除后再删班级",
            )
        teacher_count = session.exec(
            select(func.count(Teacher.id)).where(Teacher.classroom_id == room.id)
        ).one()
        if teacher_count:
            raise HTTPException(
                409,
                f"{room.name}还有 {teacher_count} 名教师，请先调整教师班级后再删除",
            )
        session.delete(room)
        session.commit()
    response.status_code = 204
    return response


@app.get("/areas", tags=["基础"])
def list_areas():
    """所有游戏区域"""
    with Session(engine) as s:
        return s.exec(select(Area)).all()


@app.get("/children", response_model=List[ChildResponse], tags=["基础"])
def list_children(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """只返回当前教师班级的幼儿。"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        return s.exec(
            select(Child).where(Child.classroom_id == teacher.classroom_id)
        ).all()


@app.post("/children", status_code=201, tags=["基础"])
def create_child(
    payload: ChildCreate,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """新增幼儿；不能借 classroom_id 把数据写进其他班级。"""
    name = required_text(payload.name, "幼儿姓名")
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        teacher = session.get(Teacher, account.teacher_id)
        if not teacher:
            raise HTTPException(500, "账号关联的教师信息不存在")
        classroom_id = payload.classroom_id or teacher.classroom_id
        if classroom_id != teacher.classroom_id:
            raise HTTPException(422, "只能向当前带班班级添加幼儿")
        child = Child(
            name=name,
            classroom_id=classroom_id,
            birth_date=payload.birth_date,
            gender={"male": Gender.MALE, "female": Gender.FEMALE}.get(payload.gender),
        )
        session.add(child)
        session.commit()
        session.refresh(child)
        return {"id": child.id, "name": child.name}


@app.get(
    "/children/{child_id}/profile",
    response_model=ChildProfileResponse,
    tags=["基础"],
)
def child_profile(
    child_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """返回当前教师班级内一名幼儿的事实型档案聚合。"""
    profile_dimensions = ("身体参与", "社会互动")
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        teacher = session.get(Teacher, account.teacher_id)
        child = session.get(Child, child_id)
        if not teacher or not child or child.classroom_id != teacher.classroom_id:
            raise HTTPException(404, "幼儿不存在")

        room = session.get(ClassRoom, child.classroom_id)
        links = session.exec(
            select(ObservationChild).where(ObservationChild.child_id == child.id)
        ).all()
        linked_ids = {link.observation_id for link in links}
        legacy_observations = session.exec(
            select(Observation).where(
                Observation.child_id == child.id,
                Observation.observer_id == teacher.id,
                Observation.classroom_id == teacher.classroom_id,
            )
        ).all()
        observations_by_id = {item.id: item for item in legacy_observations}
        if linked_ids:
            linked_observations = session.exec(
                select(Observation).where(
                    Observation.id.in_(linked_ids),
                    Observation.observer_id == teacher.id,
                    Observation.classroom_id == teacher.classroom_id,
                )
            ).all()
            observations_by_id.update({item.id: item for item in linked_observations})
        observations = list(observations_by_id.values())
        observation_ids = list(observations_by_id)

        media_rows = []
        if observation_ids:
            media_rows = session.exec(
                select(Media).where(Media.observation_id.in_(observation_ids))
            ).all()

        confirmed = sorted(
            (item for item in observations if item.status == "confirmed"),
            key=lambda item: item.observed_at,
            reverse=True,
        )
        confirmed_ids = [item.id for item in confirmed]
        tags = []
        if confirmed_ids:
            tags = session.exec(
                select(ObservationTag).where(
                    ObservationTag.observation_id.in_(confirmed_ids),
                    ObservationTag.accepted == True,  # noqa: E712
                )
            ).all()

        dimensions_by_observation = {item.id: set() for item in confirmed}
        for tag in tags:
            dimension = INDICATORS.get(tag.indicator_code, {}).get("dimension")
            if dimension in profile_dimensions:
                dimensions_by_observation[tag.observation_id].add(dimension)

        dimension_counts = {dimension: 0 for dimension in profile_dimensions}
        exported_observation_ids = set(session.exec(
            select(ExportRecord.observation_id).where(
                ExportRecord.account_id == account.id,
                ExportRecord.observation_id.in_(confirmed_ids),
            )
        ).all()) if confirmed_ids else set()
        records = []
        for observation in confirmed:
            dimensions = [
                dimension
                for dimension in profile_dimensions
                if dimension in dimensions_by_observation[observation.id]
            ]
            for dimension in dimensions:
                dimension_counts[dimension] += 1
            area = session.get(Area, observation.area_id)
            area_name = area.name if area else None
            records.append(ChildProfileRecordResponse(
                observation_id=observation.id,
                title=f"{area_name}观察记录" if area_name else "观察记录",
                area_name=area_name,
                observed_at=observation.observed_at,
                dimensions=dimensions,
                exported=observation.id in exported_observation_ids,
            ))

        evidence_times = [item.created_at for item in observations]
        evidence_times.extend(item.uploaded_at for item in media_rows)
        observed_days = {
            kindergarten_datetime(item.observed_at).date() for item in observations
        }
        observed_days.update(
            kindergarten_datetime(item.uploaded_at).date() for item in media_rows
        )
        gender = getattr(child.gender, "value", child.gender)
        return ChildProfileResponse(
            id=child.id,
            name=child.name,
            classroom_id=child.classroom_id,
            classroom_name=room.name if room else None,
            birth_date=child.birth_date,
            gender={"男": "male", "女": "female"}.get(gender),
            created_at=min(evidence_times) if evidence_times else None,
            media_count=len(media_rows),
            record_count=len(confirmed),
            observed_day_count=len(observed_days),
            dimension_counts=dimension_counts,
            records=records,
        )


@app.delete("/children/{child_id}", status_code=204, tags=["基础"])
def delete_child(
    child_id: int,
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None),
):
    """只删除没有任何素材或观察记录的幼儿，不提供级联删除。"""
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        teacher = session.get(Teacher, account.teacher_id)
        child = session.get(Child, child_id)
        if not teacher or not child or child.classroom_id != teacher.classroom_id:
            raise HTTPException(404, "幼儿不存在")

        linked_ids = set(session.exec(
            select(ObservationChild.observation_id).where(
                ObservationChild.child_id == child.id
            )
        ).all())
        linked_ids.update(session.exec(
            select(Observation.id).where(Observation.child_id == child.id)
        ).all())
        media_count = 0
        if linked_ids:
            media_count = session.exec(
                select(func.count(Media.id)).where(Media.observation_id.in_(linked_ids))
            ).one()
        record_count = len(linked_ids)
        if media_count or record_count:
            raise HTTPException(
                409,
                f"{child.name}名下还有 {media_count} 条素材、{record_count} 篇记录，请先处理后再删除",
            )

        session.delete(child)
        session.commit()
    response.status_code = 204
    return response


@app.patch("/children/{child_id}", response_model=ChildResponse, tags=["基础"])
def update_child(
    child_id: int,
    payload: ChildUpdate,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """修改已有幼儿的姓名、出生日期或性别。"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        child = s.get(Child, child_id)
        if not child or child.classroom_id != teacher.classroom_id:
            raise HTTPException(404, "幼儿不存在")

        data = payload.model_dump(exclude_unset=True)
        if data.get("name", "present") is None:
            raise HTTPException(422, "幼儿姓名不能为 null")
        for key, value in data.items():
            setattr(child, key, value)
        s.add(child)
        s.commit()
        s.refresh(child)
        return child


@app.get("/teachers", response_model=List[TeacherResponse], tags=["基础"])
def list_teachers(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """只返回当前登录教师；园所成员列表使用园所专用接口。"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        return [teacher]


@app.patch("/teachers/{teacher_id}", response_model=TeacherResponse, tags=["基础"])
def update_teacher(
    teacher_id: int,
    payload: TeacherUpdate,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """修改已有教师的姓名。"""
    with Session(engine) as s:
        _, current_teacher = authenticated_teacher(s, request, authorization)
        teacher = s.get(Teacher, teacher_id)
        if not teacher or teacher.id != current_teacher.id:
            raise HTTPException(404, "教师不存在")

        data = payload.model_dump(exclude_unset=True)
        if data.get("name", "present") is None:
            raise HTTPException(422, "教师姓名不能为 null")
        for key, value in data.items():
            setattr(teacher, key, value)
        s.add(teacher)
        s.commit()
        s.refresh(teacher)
        return teacher


@app.get("/indicators", tags=["基础"])
def list_indicators():
    """观察指标字典（4 个维度 × 若干要点 × 3 层级）"""
    return all_indicators_flat()


# ============================================================
# 1. 上传素材
# ============================================================

@app.post(
    "/uploads",
    status_code=201,
    response_model=MediaResponse,
    tags=["1·素材"],
)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    observation_id: int = Query(..., description="当前账号拥有的待上传观察记录 id"),
    duration_sec: Optional[int] = Query(
        None, description="视频时长（秒）。指标 1.1 的层级分界靠它纯计算得出，零幻觉。照片可不填。"
    ),
    authorization: Optional[str] = Header(None),
):
    """上传素材并直接绑定到当前教师拥有的待上传记录。"""
    content_type, ext = resolve_upload_type(file)
    stored_filename = f"{uuid4().hex}{ext}"
    stored_path = UPLOAD_DIR / stored_filename
    size = 0

    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        observation = owned_observation(s, teacher, observation_id)
        if observation.status != "uploaded":
            raise HTTPException(409, "这条记录已经进入整理阶段，不能继续上传素材")

        try:
            with stored_path.open("wb") as destination:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_SIZE:
                        raise HTTPException(413, "文件不能超过 200MB")
                    destination.write(chunk)

            real_duration_sec = duration_sec
            if content_type.startswith("video/"):
                probed = _probe_video_duration(stored_path)
                if probed is not None:
                    real_duration_sec = int(round(probed))
                if probed is not None and probed > MAX_DURATION_SEC:
                    raise HTTPException(
                        422,
                        "视频太长了，建议录 1~3 分钟的片段。超过 3 分钟会影响白描效果，请缩短后再上传。",
                    )
                generate_video_thumbnail(stored_path)

            media = Media(
                stored_filename=stored_filename,
                content_type=content_type,
                size=size,
                duration_sec=real_duration_sec,
                observation_id=observation.id,
            )
            if observation.media_type is None:
                observation.media_type = "video" if content_type.startswith("video/") else "image"
            s.add(media)
            s.add(observation)
            s.commit()
            s.refresh(media)
            return media_response(media)
        except Exception:
            for artifact in (
                stored_path,
                get_thumbnail_path(stored_filename),
                get_thumbnail_error_path(stored_filename),
            ):
                artifact.unlink(missing_ok=True)
            raise


@app.get("/media", response_model=List[MediaResponse], tags=["1·素材"])
def list_media(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """当前教师观察记录绑定的全部素材。"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        observation_ids = select(Observation.id).where(
            Observation.observer_id == teacher.id,
            Observation.classroom_id == teacher.classroom_id,
        )
        rows = s.exec(
            select(Media).where(Media.observation_id.in_(observation_ids))
        ).all()
        return [media_response(media) for media in rows]


@app.get(
    "/media/{media_id}/file",
    response_class=FileResponse,
    responses={
        200: {
            "description": "素材文件",
            "content": {
                "image/jpeg": {},
                "image/png": {},
                "image/heic": {},
                "image/heif": {},
                "video/mp4": {},
                "video/quicktime": {},
            },
        },
    },
    tags=["1·素材"],
)
def get_media_file(
    media_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """读取一份已上传素材，供前端展示图片或视频首帧。"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        media = owned_media(s, teacher, media_id)

        if Path(media.stored_filename).name != media.stored_filename:
            raise HTTPException(404, "素材文件不存在")
        stored_path = UPLOAD_DIR / media.stored_filename
        if not stored_path.is_file():
            raise HTTPException(404, "素材文件不存在")

        return FileResponse(stored_path, media_type=media.content_type)


@app.get(
    "/media/{media_id}/thumbnail",
    response_class=FileResponse,
    responses={
        200: {"description": "视频缩略图", "content": {"image/png": {}}},
        404: {"description": "缩略图不可用，响应包含失败原因"},
    },
    tags=["1·素材"],
)
def get_media_thumbnail(
    media_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """返回服务端生成的视频缩略图；历史视频首次读取时补生成。"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        media = owned_media(s, teacher, media_id)
        if not media.content_type.startswith("video/"):
            raise HTTPException(400, "图片素材无需生成视频缩略图")
        if Path(media.stored_filename).name != media.stored_filename:
            raise HTTPException(404, "素材文件不存在")

        source_path = UPLOAD_DIR / media.stored_filename
        if not source_path.is_file():
            raise HTTPException(404, "素材文件不存在")

        thumbnail_path = get_thumbnail_path(media.stored_filename)
        failure_reason = get_thumbnail_failure_reason(media.stored_filename)
        if not thumbnail_path.is_file():
            failure_reason = generate_video_thumbnail(source_path)

        if thumbnail_path.is_file():
            return FileResponse(thumbnail_path, media_type="image/png")

        raise HTTPException(
            404,
            detail={
                "message": "视频缩略图不可用",
                "reason": failure_reason or "视频缩略图生成失败",
            },
        )


# ============================================================
# 2. 观察记录
# ============================================================

@app.post("/observations", status_code=201, tags=["2·观察记录"])
def create_observation(
    payload: ObservationCreate,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """现场新建观察记录；只要求游戏区，状态固定为 uploaded。"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        room = s.get(ClassRoom, teacher.classroom_id)
        if not room:
            raise HTTPException(500, "账号关联的班级信息不存在")
        child = s.get(Child, payload.child_id) if payload.child_id is not None else None
        if payload.child_id is not None and (
            not child or child.classroom_id != teacher.classroom_id
        ):
            raise HTTPException(404, "幼儿不存在")
        observation = Observation(
            child_id=payload.child_id,
            area_id=payload.area_id,
            classroom_id=room.id,
            observer_id=teacher.id,
            age_group=room.age_group,
            media_type=None,
            note=payload.note,
            location=payload.location,
            background_note=payload.background_note,
            status="uploaded",
        )
        s.add(observation)
        s.flush()
        sync_primary_child(s, observation.id, payload.child_id)
        s.commit()
        s.refresh(observation)
        return observation


def observed_at_day_bounds(
    date_from: Optional[date],
    date_to: Optional[date],
):
    """观察日期（北京时间自然日）→ 半开时间区间 [起, 止+1 天)。

    观察文书统一按 Asia/Shanghai 展示与判断日期（“今天”“本月”都是这么算的），
    检索也必须用同一把尺子：date_from/date_to 指幼儿园当地的自然日，
    这里把“当地零点”换算成明确的 UTC 时刻交给 SQL 比较，
    避免在 Python 里把整表拉下来再逐条转时区。
    返回的 datetime 都带 Asia/Shanghai 时区；绑定参数时 UTCDateTime 会统一转 UTC。
    """
    def local_day_start(day: date) -> datetime:
        return datetime(day.year, day.month, day.day, tzinfo=KINDERGARTEN_TIMEZONE)

    start = local_day_start(date_from) if date_from is not None else None
    end_exclusive = (
        local_day_start(date_to + timedelta(days=1)) if date_to is not None else None
    )
    return start, end_exclusive


@app.get(
    "/observations",
    response_model=List[ObservationResponse],
    tags=["2·观察记录"],
)
def list_observations(
    request: Request,
    status: Optional[ObservationStatus] = Query(None, description="按处理状态过滤"),
    child_id: Optional[int] = Query(
        None, description="按幼儿过滤：该幼儿是主角或关联幼儿的记录都会返回"
    ),
    area_id: Optional[int] = Query(None, description="按游戏区域过滤"),
    date_from: Optional[date] = Query(
        None,
        description="观察日期（北京时间）起始日，含当天，格式 YYYY-MM-DD",
    ),
    date_to: Optional[date] = Query(
        None,
        description="观察日期（北京时间）截止日，含当天，格式 YYYY-MM-DD",
    ),
    indicator_code: Optional[str] = Query(
        None, description="按已采纳指标编码过滤，如 1.3"
    ),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    offset: int = Query(0, ge=0, description="跳过数量"),
    authorization: Optional[str] = Header(None),
):
    """当前教师的观察记录，可组合筛选并按观察时间倒序分页。"""
    if (
        date_from is not None
        and date_to is not None
        and date_from > date_to
    ):
        raise HTTPException(422, "date_from 不能晚于 date_to")
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        child = s.get(Child, child_id) if child_id is not None else None
        if child_id is not None and (
            not child or child.classroom_id != teacher.classroom_id
        ):
            raise HTTPException(404, "幼儿不存在")
        if area_id is not None and s.get(Area, area_id) is None:
            raise HTTPException(404, f"找不到 id={area_id} 的游戏区域")
        if indicator_code is not None and indicator_code not in INDICATORS:
            raise HTTPException(404, "观察指标不存在")

        statement = select(Observation).where(
            Observation.observer_id == teacher.id,
            Observation.classroom_id == teacher.classroom_id,
        )
        if status is not None:
            statement = statement.where(Observation.status == status)
        if area_id is not None:
            statement = statement.where(Observation.area_id == area_id)
        if child_id is not None:
            # 多人素材会写 observation_child 关联表；老记录可能只落 observation.child_id。
            # 两边都认，才能保证“按幼儿检索”不漏旧数据。
            linked_ids = select(ObservationChild.observation_id).where(
                ObservationChild.child_id == child_id
            )
            statement = statement.where(
                or_(
                    Observation.id.in_(linked_ids),
                    Observation.child_id == child_id,
                )
            )
        if indicator_code is not None:
            tagged_ids = select(ObservationTag.observation_id).where(
                ObservationTag.indicator_code == indicator_code,
                ObservationTag.accepted == True,  # noqa: E712
            )
            statement = statement.where(Observation.id.in_(tagged_ids))
        if date_from is not None or date_to is not None:
            start, end_exclusive = observed_at_day_bounds(date_from, date_to)
            if start is not None:
                statement = statement.where(Observation.observed_at >= start)
            if end_exclusive is not None:
                statement = statement.where(Observation.observed_at < end_exclusive)
        statement = statement.order_by(
            Observation.observed_at.desc(), Observation.id.desc()
        ).offset(offset).limit(limit)
        return s.exec(statement).all()


@app.post("/observations/{obs_id}/attach-media", tags=["2·观察记录"])
def attach_media(
    obs_id: int,
    request: Request,
    media_id: int = Query(..., description="要绑定的素材 id"),
    authorization: Optional[str] = Header(None),
):
    """兼容旧客户端：只允许确认素材已绑定到同一条自有记录。"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)
        media = owned_media(s, teacher, media_id)
        if media.observation_id != obs.id:
            raise HTTPException(404, "素材不存在")
        if obs.status != "uploaded":
            raise HTTPException(
                400,
                detail={
                    "message": f"状态为 {obs.status} 时不能绑定素材",
                    "current_status": obs.status,
                    "target_status": "uploaded",
                },
            )

        return {"ok": True, "observation_id": obs_id, "media_id": media_id,
                "media_type": obs.media_type, "status": obs.status}


def observation_child_ids(session: Session, obs: Observation) -> List[int]:
    links = session.exec(select(ObservationChild).where(
        ObservationChild.observation_id == obs.id
    ).order_by(ObservationChild.is_primary.desc(), ObservationChild.child_id)).all()
    return [link.child_id for link in links] or ([obs.child_id] if obs.child_id else [])


def context_digest(session: Session, obs: Observation, *, narrative=False, mode="focused") -> str:
    data = {"children": observation_child_ids(session, obs), "area": obs.area_id,
            "age": obs.age_group, "note": obs.note or "",
            "purpose": (obs.purpose or "").strip() if mode == "focused" else ""}
    if narrative:
        data["narrative"] = obs.narrative or ""
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def latest_workflow_run(session: Session, obs: Observation, workflow: str):
    return session.exec(select(AIRun).where(
        AIRun.observation_id == obs.id, AIRun.workflow == workflow
    ).order_by(AIRun.id.desc())).first()


def run_context(run):
    return (run.response_raw or {}).get("_bangbang_context", {}) if run else {}


def narrative_context_changed(session: Session, obs: Observation) -> bool:
    context = run_context(latest_workflow_run(session, obs, "narrative"))
    return bool(context and context.get("identity_digest", context.get("digest")) != context_digest(
        session, obs, mode=context.get("mode", "focused")))


def suggestions_current(session: Session, obs: Observation) -> bool:
    context = run_context(latest_workflow_run(session, obs, "indicator_suggestion"))
    return bool(context and context.get("digest") == context_digest(session, obs, narrative=True))


def current_observation_tags(session: Session, obs: Observation):
    """旧轮次留在数据库用于审计，不混入当前判断和导出。无 AI run 的手工历史条目兼容保留。"""
    tags = session.exec(select(ObservationTag).where(ObservationTag.observation_id == obs.id)).all()
    run = latest_workflow_run(session, obs, "indicator_suggestion")
    current = suggestions_current(session, obs)
    return [tag for tag in tags if (tag.ai_run_id is None and run is None) or
            (current and tag.ai_run_id == run.id)]


def subject_prompt(session: Session, obs: Observation) -> str:
    aliases = [ai_service._child_alias(i) for i, _ in enumerate(observation_child_ids(session, obs))]
    if not aliases:
        roles = "尚未对应姓名，请记录能够区分的幼儿，并保持同一人物代号一致"
    else:
        roles = "主观察幼儿：" + aliases[0] + "。同时记录的其他幼儿：" + ("、".join(aliases[1:]) or "未选择")
        roles += "。分析以主观察幼儿的行为为依据，其他幼儿的行为只提供互动背景，不得移到主观察幼儿身上"
    return roles + "。衣着位置提示：" + (obs.note or "未提供，无法仅凭名单确定画面中谁是主体；不得凭出场顺序或行为多少猜测身份，人物对应需教师核对")



@app.put("/observations/{obs_id}/children", tags=["2·观察记录"])
def replace_observation_children(
    obs_id: int,
    payload: ObservationChildrenUpdate,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """全量替换素材中的幼儿关联；第一个幼儿同步为记录主角。"""
    child_ids = list(dict.fromkeys(payload.child_ids))
    if not child_ids:
        raise HTTPException(422, "请至少选择一名幼儿")
    with Session(engine) as session:
        _, teacher = authenticated_teacher(session, request, authorization)
        observation = owned_observation(session, teacher, obs_id)
        if observation.status not in {"uploaded", "ready_for_review", "failed"}:
            raise HTTPException(400, f"状态为 {observation.status} 时不能修改观察幼儿")

        children = [session.get(Child, child_id) for child_id in child_ids]
        if any(
            child is None or child.classroom_id != observation.classroom_id
            for child in children
        ):
            raise HTTPException(422, "所选幼儿必须都在当前班级")

        old_links = session.exec(
            select(ObservationChild).where(
                ObservationChild.observation_id == observation.id
            )
        ).all()
        for link in old_links:
            session.delete(link)
        observation.child_id = child_ids[0]
        session.add(observation)
        for index, child_id in enumerate(child_ids):
            session.add(ObservationChild(
                observation_id=observation.id,
                child_id=child_id,
                is_primary=index == 0,
            ))
        session.commit()
        return {"child_ids": child_ids}


@app.patch("/observations/{obs_id}", tags=["2·观察记录"])
def update_observation(
    obs_id: int,
    payload: ObservationUpdate,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """教师补幼儿和现场说明，或修改观察目的 / 白描 / 分析 / 措施。"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)

        data = payload.model_dump(exclude_unset=True)

        context_fields = {"child_id", "note", "purpose", "narrative"} & data.keys()
        if context_fields and obs.status not in {"uploaded", "ready_for_review", "failed", "confirmed"}:
            raise HTTPException(
                400,
                detail={
                    "message": f"状态为 {obs.status} 时不能更新 child_id 或 note",
                    "current_status": obs.status,
                },
            )
        if "child_id" in data and data["child_id"] is not None:
            child = s.get(Child, data["child_id"])
            if not child or child.classroom_id != teacher.classroom_id:
                raise HTTPException(404, "幼儿不存在")

        if obs.status == "confirmed" and any(
            key in data and (data[key] or "") != (getattr(obs, key) or "")
            for key in {"child_id", "note", "purpose", "narrative"}
        ) or (obs.status == "confirmed" and any(key in data and not (data[key] or "").strip() for key in {"analysis", "strategy"})):
            transition_observation(obs, "ready_for_review")
            obs.confirmed_at = None

        # 教师动过 AI 白描 → 来源自动从 ai 变成 ai_edited
        if "narrative" in data and obs.narrative_source == "ai":
            if data["narrative"] != obs.narrative:
                obs.narrative_source = "ai_edited"

        for k, v in data.items():
            setattr(obs, k, v)

        if "child_id" in data:
            sync_primary_child(s, obs.id, data["child_id"])

        s.add(obs)
        s.commit()
        s.refresh(obs)
        return obs


def require_analysis_and_strategy(obs: Observation):
    missing = [label for field, label in [("analysis", "观察分析"), ("strategy", "支持策略")] if not (getattr(obs, field) or "").strip()]
    if missing:
        raise HTTPException(400, "请填写" + "和".join(missing))


@app.post("/observations/{obs_id}/confirm", tags=["2·观察记录"])
def confirm_observation(
    obs_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """教师定稿。要求幼儿、观察目标、白描和至少一个已采纳的指标都到位。"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)
        ensure_status_transition(obs, "confirmed")
        if obs.child_id is None:
            raise HTTPException(400, "请先选择这条记录关于哪位幼儿")
        if not obs.purpose or not obs.purpose.strip():
            raise HTTPException(400, "请至少填写一个观察目标")
        if not obs.narrative:
            raise HTTPException(400, "还没有白描，不能定稿")

        if narrative_context_changed(s, obs):
            raise HTTPException(409, "观察对象或目标已改变，请重新生成并核对白描")
        accepted = [tag for tag in current_observation_tags(s, obs) if tag.accepted is True]
        if not accepted:
            raise HTTPException(400, "还没有任何已采纳的指标，不能定稿")

        require_analysis_and_strategy(obs)
        transition_observation(obs, "confirmed")
        s.add(obs)
        s.commit()
        s.refresh(obs)
        return {"ok": True, "observation": obs, "accepted_tag_count": len(accepted)}


@app.delete("/observations/{obs_id}", status_code=204, tags=["2·观察记录"])
def delete_observation(
    obs_id: int,
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None),
):
    """删除一条观察记录及其全部数据。

    用于清理导入的测试记录：会一并删除该记录绑定的素材（含磁盘文件）、
    观察指标、多人关联和 AI 调用审计。属于明确的"整条记录做删除"。
    """
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)
        # 素材：删除数据库记录 + 磁盘文件与缩略图
        media_list = s.exec(
            select(Media).where(Media.observation_id == obs_id)
        ).all()
        for media in media_list:
            for path in (
                UPLOAD_DIR / media.stored_filename,
                get_thumbnail_path(media.stored_filename),
                get_thumbnail_error_path(media.stored_filename),
            ):
                try:
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass
            s.delete(media)

        # 关联表 / 指标 / AI 审计
        for link in s.exec(
            select(ObservationChild).where(ObservationChild.observation_id == obs_id)
        ).all():
            s.delete(link)
        for tag in s.exec(
            select(ObservationTag).where(ObservationTag.observation_id == obs_id)
        ).all():
            s.delete(tag)
        for run in s.exec(
            select(AIRun).where(AIRun.observation_id == obs_id)
        ).all():
            s.delete(run)

        s.delete(obs)
        s.commit()
    response.status_code = 204
    return response


# ============================================================
# 3. AI 环节（当前为 DEMO MOCK）
# ============================================================

@app.post(
    "/observations/{obs_id}/narrative",
    response_model=NarrativeGenerationResponse,
    tags=["3·AI"],
)
def generate_narrative(
    obs_id: int,
    request: Request,
    mode: Literal["focused", "explore"] = Query("focused"),
    authorization: Optional[str] = Header(None),
):
    """
    【AI 工作流 A】根据绑定的素材生成客观白描。
    结果写入 narrative + narrative_ai_raw，来源标记为 ai。
    """
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)

        if mode == "focused" and not (obs.purpose or "").strip():
            raise HTTPException(400, "请先选择或添加观察目标；暂无目标可选先看看素材")
        names = classroom_child_names_for_anonymization(s, obs)
        purpose = ai_service._anonymize_narrative(obs.purpose or "", names) if mode == "focused" else ""
        subjects = ai_service._anonymize_narrative(subject_prompt(s, obs), names)
        input_digest = context_digest(s, obs, mode=mode)
        area = s.get(Area, obs.area_id)
        media = s.exec(
            select(Media).where(Media.observation_id == obs_id)
        ).first()
        if not media:
            raise HTTPException(400, "这条记录还没绑定素材，请先调用 attach-media")

        transition_observation(obs, "processing")
        s.add(obs)
        s.commit()
        s.refresh(obs)

        vision_frames = _media_vision_frames(media)

        # 音频转写：仅视频抽取语音（照片无音轨）；失败降级为 mock，不影响白描。
        transcript = None
        asr = None
        if media.content_type.startswith("video/"):
            media_path = UPLOAD_DIR / media.stored_filename
            if media_path.is_file():
                asr = asr_service.transcribe_video(media_path, duration_sec=media.duration_sec)
                if asr and not asr.get("is_mock"):
                    transcript = ai_service._anonymize_narrative(asr.get("transcript") or "", names)

        # 预选人数只作提示；未选时由素材中的可见人物确定，不默认单人。
        child_count_hint = len(s.exec(
            select(ObservationChild).where(ObservationChild.observation_id == obs_id)
        ).all()) or None

        try:
            result = ai_service.generate_narrative(
                area_code=area.code if area else "",
                area_name=area.name if area else None,
                media_type=obs.media_type,
                duration_sec=media.duration_sec,
                frames=vision_frames,
                transcript=transcript,
                child_count_hint=child_count_hint,
                purpose=purpose,
                subject_context=subjects,
            )
        except Exception as exc:
            transition_observation(
                obs,
                "failed",
                failure_reason=f"生成客观白描失败：{exc}",
            )
            s.add(obs)
            s.commit()
            raise HTTPException(500, obs.failure_reason) from exc

        obs.narrative = result["narrative"]
        obs.narrative_ai_raw = result["narrative"]   # 留底，用来对比教师改了多少
        obs.narrative_source = "ai"
        transition_observation(obs, "ready_for_review")
        s.add(obs)
        metadata = result.get("ai_run") or {
            "workflow": "narrative", "provider": "mock", "model": result["engine"],
            "prompt_version": "wf-a-context-v1", "status": "completed", "is_mock": True,
            "prompt_rendered": "mock 模式未发送外部请求",
        }
        metadata["response_raw"] = {**(metadata.get("response_raw") or {}),
            "_bangbang_context": {"mode": mode, "digest": input_digest}}
        s.add(AIRun(observation_id=obs_id, **metadata))
        s.commit()
        s.refresh(obs)

        return {
            "observation_id": obs_id,
            "status": obs.status,
            "processing_started_at": obs.processing_started_at,
            "ready_at": obs.ready_at,
            "narrative": result["narrative"],
            "is_mock": result["is_mock"],
            "engine": result["engine"],
            "notice": result["notice"],
            "asr": asr,
        }


@app.post("/observations/{obs_id}/people", tags=["3·AI"])
def observation_people(obs_id: int, request: Request, authorization: Optional[str] = Header(None)):
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)
        if not (obs.narrative or "").strip():
            raise HTTPException(400, "请先生成白描")
        digest = hashlib.sha256(obs.narrative.encode()).hexdigest()
        run = latest_workflow_run(s, obs, "person_grouping")
        raw = (run.response_raw or {}) if run else {}
        if raw.get("digest") == digest:
            return {**raw["result"], "narrative": obs.narrative}
        result = person_service.identify_people(obs.narrative, classroom_child_names_for_anonymization(s, obs))
        s.add(AIRun(observation_id=obs_id, workflow="person_grouping", provider=result["method"], model="narrative-person-grouping",
                    prompt_version="person-grouping-v1", status="completed", is_mock=result["method"] == "rules",
                    prompt_rendered="只依据白描衣着、位置及行为归组；不推断身份", response_raw={"digest": digest, "result": result}))
        s.commit()
        return {**result, "narrative": obs.narrative}


@app.post("/observations/{obs_id}/people/assign", tags=["4·教师确认"])
def assign_observation_people(obs_id: int, payload: PeopleAssignment, request: Request, authorization: Optional[str] = Header(None)):
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)
        if obs.status not in {"ready_for_review", "confirmed"}:
            raise HTTPException(400, "请等待白描完成后对应姓名")
        if payload.narrative != obs.narrative:
            raise HTTPException(409, "白描已修改，请重新整理人物后再代入")
        if narrative_context_changed(s, obs):
            raise HTTPException(409, "观察目标或人物提示已改变，请先重新生成白描")
        refs = person_service.references(obs.narrative, classroom_child_names_for_anonymization(s, obs))
        names, ids = {}, []
        for assignment in payload.assignments:
            child = s.get(Child, assignment.child_id)
            if not child or child.classroom_id != teacher.classroom_id:
                raise HTTPException(404, "幼儿不存在")
            if not assignment.ref_indexes:
                raise HTTPException(422, "请选择要对应的人物")
            ids.append(child.id)
            for i in assignment.ref_indexes:
                if i < 0 or i >= len(refs) or refs[i]['group'] or i in names:
                    raise HTTPException(422, "人物引用无效或重复")
                names[i] = child.name
        if not names:
            raise HTTPException(422, "请至少为一位幼儿选择姓名")
        original_ids = observation_child_ids(s, obs)
        # Preserve earlier assignments in partial mapping and the original selected subjects.
        ids = list(dict.fromkeys(original_ids + ids))
        text = obs.narrative
        for i in sorted(names, reverse=True):
            ref = refs[i]
            text = text[:ref['start']] + names[i] + text[ref['end']:]
        obs.narrative = text
        obs.narrative_source = "ai_edited"
        obs.child_id = ids[0]
        for i, child_id in enumerate(ids):
            link = s.get(ObservationChild, (obs_id, child_id))
            if not link:
                link = ObservationChild(observation_id=obs_id, child_id=child_id, is_primary=i == 0)
            s.add(link)
        if obs.status == "confirmed":
            transition_observation(obs, "ready_for_review")
            obs.confirmed_at = None
        s.add(obs)
        s.flush()
        run = latest_workflow_run(s, obs, "narrative")
        if run and run_context(run):
            raw = dict(run.response_raw or {})
            context = dict(run_context(run))
            context["identity_digest"] = context_digest(s, obs, mode=context.get("mode", "focused"))
            context["identity_confirmed_at"] = utc_now().isoformat()
            raw["_bangbang_context"] = context
            run.response_raw = raw
            s.add(run)
        s.commit()
        return {"narrative": obs.narrative, "child_ids": ids}


@app.post("/observations/{obs_id}/suggest-tags", tags=["3·AI"])
def suggest_tags(
    obs_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    【AI 工作流 B】根据白描 + 区域 + 年龄段，推荐 2-3 个候选指标。

    系统判定与 AI 建议分别落库：
    - quant_hits → source=system_determined、accepted=True（默认选中）
    - suggestions → source=ai_suggested、accepted=None（等待教师决定）
    """
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)
        if not observation_child_ids(s, obs):
            raise HTTPException(400, "请先选择观察幼儿")
        if not (obs.purpose or "").strip():
            raise HTTPException(400, "请先选择或添加观察目标")
        if narrative_context_changed(s, obs):
            raise HTTPException(409, "观察对象或目标已改变，请重新生成并核对白描")
        if obs.status == "processing":
            raise HTTPException(409, "正在整理，请稍后再试")
        if not obs.narrative:
            raise HTTPException(400, "还没有白描，请先调用 narrative 接口")

        if obs.status == "failed":
            transition_observation(obs, "processing")
            s.add(obs)
            s.commit()
            s.refresh(obs)
        elif obs.status not in {"processing", "ready_for_review"}:
            ensure_status_transition(obs, "ready_for_review")

        area = s.get(Area, obs.area_id)
        media = s.exec(select(Media).where(Media.observation_id == obs_id)).first()

        existing_candidates = [tag for tag in current_observation_tags(s, obs)
                               if tag.source in {"system_determined", "ai_suggested"}]
        if suggestions_current(s, obs):
            system_tags = [t for t in existing_candidates if t.source == "system_determined"]
            ai_tags = [t for t in existing_candidates if t.source == "ai_suggested"]
            linked_run = latest_workflow_run(s, obs, "indicator_suggestion")
            return {
                "observation_id": obs_id,
                "status": obs.status,
                "processing_started_at": obs.processing_started_at,
                "ready_at": obs.ready_at,
                "suggestions": [{
                    "tag_id": tag.id,
                    "indicator_code": tag.indicator_code,
                    "indicator_name": tag.indicator_name,
                    "level": tag.level,
                    "level_desc": level_desc(tag.indicator_code, tag.level),
                    "confidence": tag.confidence,
                    "reason": tag.ai_reason,
                    "evidence_based": (tag.confidence or 0) > 0.42,
                    "rank": tag.rank_in_suggestion,
                } for tag in ai_tags],
                "quant_hits": [{
                    "tag_id": tag.id,
                    "indicator_code": tag.indicator_code,
                    "indicator_name": tag.indicator_name,
                    "level": tag.level,
                    "level_desc": level_desc(tag.indicator_code, tag.level),
                    "basis": tag.ai_reason,
                    "deterministic": True,
                    "accepted": tag.accepted,
                } for tag in system_tags],
                "is_mock": linked_run.is_mock if linked_run else True,
                "engine": linked_run.model if linked_run else "persisted-candidates",
                "notice": "返回已保存的候选指标，未重复生成。",
                "hint": "quant_hits 是纯计算命中（如视频时长），不走模型，界面上应标为「系统判定」而非「AI 建议」。",
            }

        input_digest = context_digest(s, obs, narrative=True)
        if obs.status != "processing":
            transition_observation(obs, "processing")
            s.add(obs)
            s.commit()

        try:
            result = ai_service.suggest_indicators(
                narrative=obs.narrative,
                area_code=area.code if area else "",
                area_name=area.name if area else "",
                age_group=obs.age_group,
                duration_sec=media.duration_sec if media else None,
                child_names=classroom_child_names_for_anonymization(s, obs),
                purpose=obs.purpose.strip(),
                subject_context=subject_prompt(s, obs),
            )
        except Exception as exc:
            transition_observation(
                obs,
                "failed",
                failure_reason=f"生成候选指标失败：{exc}",
            )
            s.add(obs)
            s.commit()
            raise HTTPException(500, obs.failure_reason) from exc

        result["ai_run"]["response_raw"] = {**(result["ai_run"].get("response_raw") or {}),
            "_bangbang_context": {"digest": input_digest}}
        run = AIRun(observation_id=obs_id, **result["ai_run"])
        s.add(run)
        s.flush()

        saved_quant_hits = []
        for hit in result["quant_hits"]:
            tag = ObservationTag(
                observation_id=obs_id,
                ai_run_id=run.id,
                indicator_code=hit["indicator_code"],
                indicator_name=hit["indicator_name"],
                level=hit["level"],
                source="system_determined",
                accepted=True,
                ai_reason=hit["basis"],
            )
            s.add(tag)
            s.flush()
            saved_quant_hits.append({
                "tag_id": tag.id,
                "indicator_code": tag.indicator_code,
                "indicator_name": tag.indicator_name,
                "level": tag.level,
                "level_desc": hit["level_desc"],
                "basis": hit["basis"],
                "deterministic": True,
                "accepted": tag.accepted,
            })

        saved = []
        for sug in result["suggestions"]:
            tag = ObservationTag(
                observation_id=obs_id,
                ai_run_id=run.id,
                indicator_code=sug["indicator_code"],
                indicator_name=sug["indicator_name"],
                level=sug["level"],
                source="ai_suggested",
                accepted=None,
                confidence=sug["confidence"],
                ai_reason=sug["reason"],
                rank_in_suggestion=sug["rank"],
            )
            s.add(tag)
            s.flush()
            saved.append({
                "tag_id": tag.id,
                "indicator_code": tag.indicator_code,
                "indicator_name": tag.indicator_name,
                "level": tag.level,
                "level_desc": sug["level_desc"],
                "confidence": tag.confidence,
                "reason": tag.ai_reason,
                "evidence_based": sug["evidence_based"],
                "rank": tag.rank_in_suggestion,
            })

        if obs.status == "processing":
            transition_observation(obs, "ready_for_review")
        s.add(obs)
        s.commit()
        s.refresh(obs)

        return {
            "observation_id": obs_id,
            "status": obs.status,
            "processing_started_at": obs.processing_started_at,
            "ready_at": obs.ready_at,
            "suggestions": saved,
            "quant_hits": saved_quant_hits,
            "is_mock": result["is_mock"],
            "engine": result["engine"],
            "notice": result["notice"],
            "ai_run_id": run.id,
            "hint": "quant_hits 是纯计算命中（如视频时长），不走模型，界面上应标为「系统判定」而非「AI 建议」。",
        }


@app.post(
    "/observations/{obs_id}/suggest-analysis",
    response_model=AnalysisSuggestionResponse,
    tags=["3·AI"],
)
def suggest_analysis(
    obs_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """【AI 工作流 C】根据白描 + 已确认指标，给出「观察分析 + 下一步支持策略」的思路支架。

    返回的 analysis / strategy 是**可改写的建议**，教师据此自行定稿；与教师的正式分析/措施分开返回与展示。
    真实走 DeepSeek，失败降级为规则支架（is_mock=True）。
    """
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)
        area = s.get(Area, obs.area_id)

        accepted = [tag for tag in current_observation_tags(s, obs) if tag.accepted is True]
        indicator_names = [tag.indicator_name for tag in accepted if tag.indicator_name]

        result = ai_service.suggest_analysis_and_strategy(
            narrative=obs.narrative or "",
            area_name=area.name if area else None,
            indicator_names=indicator_names,
            child_count_hint=len(s.exec(
                select(ObservationChild).where(ObservationChild.observation_id == obs_id)
            ).all()) or 1,
        )
        if result.get("ai_run"):
            s.add(AIRun(observation_id=obs_id, **result["ai_run"]))
            s.commit()

        return {
            "observation_id": obs_id,
            "analysis": result["analysis"],
            "strategy": result["strategy"],
            "is_mock": result["is_mock"],
            "engine": result["engine"],
            "notice": result["notice"],
        }


# ============================================================
# 4. 教师确认环节
# ============================================================

@app.get("/observations/{obs_id}/tags", tags=["4·教师确认"])
def list_tags(
    obs_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """这条记录上所有指标标注"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)
        return current_observation_tags(s, obs)


@app.patch("/observations/{obs_id}/tags/{tag_id}", tags=["4·教师确认"])
def decide_tag(
    obs_id: int,
    tag_id: int,
    decision: TagDecision,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    教师采纳或否掉一条 AI 候选，或取消 / 恢复一条系统判定。
    AI 建议的 accepted 字段是「AI 候选采纳率」的数据来源。
    """
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)
        tag = s.get(ObservationTag, tag_id)
        if not tag or tag.observation_id != obs_id:
            raise HTTPException(404, "标注不存在")

        if tag.id not in {item.id for item in current_observation_tags(s, obs)}:
            raise HTTPException(409, "观察内容已更新，请重新推荐指标")

        tag.accepted = decision.accepted
        tag.resolved_at = utc_now()
        s.add(tag)
        s.commit()
        s.refresh(tag)
        return {"ok": True, "tag": tag,
                "note": "采纳" if decision.accepted else "已否掉"}


@app.post("/observations/{obs_id}/tags", status_code=201, tags=["4·教师确认"])
def add_tag_by_teacher(
    obs_id: int,
    payload: TagCreate,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    教师自己补一个 AI 没想到的指标。
    source=teacher_added，这类记录用于计算「AI 漏检率」。
    """
    item = INDICATORS.get(payload.indicator_code)
    if not item:
        raise HTTPException(400, f"指标 {payload.indicator_code} 不存在")
    if payload.level not in (1, 2, 3):
        raise HTTPException(400, "level 只能是 1、2、3")

    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)

        latest_run = latest_workflow_run(s, obs, "indicator_suggestion")
        if latest_run and not suggestions_current(s, obs):
            raise HTTPException(409, "观察内容已更新，请先重新推荐指标")

        tag = ObservationTag(
            observation_id=obs_id,
            ai_run_id=latest_run.id if latest_run else None,
            indicator_code=payload.indicator_code,
            indicator_name=item["name"],
            level=payload.level,
            source="teacher_added",
            accepted=True,          # 教师自己加的，默认就是采纳
            resolved_at=utc_now(),
        )
        s.add(tag)
        s.commit()
        s.refresh(tag)
        return tag


# ============================================================
# 5. 完整记录 & 指标
# ============================================================

@app.get(
    "/observations/{obs_id}",
    response_model=ObservationDetailResponse,
    tags=["5·成果"],
)
def get_observation_detail(
    obs_id: int,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """一条观察记录的完整内容：四段正文 + 素材 + 已采纳的指标"""
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        obs = owned_observation(s, teacher, obs_id)

        child = s.get(Child, obs.child_id) if obs.child_id is not None else None
        observer = s.get(Teacher, obs.observer_id) if obs.observer_id is not None else None
        area = s.get(Area, obs.area_id)
        room = s.get(ClassRoom, obs.classroom_id) if obs.classroom_id else None
        media = s.exec(select(Media).where(Media.observation_id == obs_id)).all()
        tags = current_observation_tags(s, obs)
        child_links = s.exec(
            select(ObservationChild)
            .where(ObservationChild.observation_id == obs_id)
            .order_by(ObservationChild.is_primary.desc(), ObservationChild.child_id)
        ).all()
        related_children = []
        for link in child_links:
            related_child = s.get(Child, link.child_id)
            if not related_child:
                continue
            related_children.append(RelatedChildResponse(
                id=related_child.id,
                name=related_child.name,
                classroom_id=related_child.classroom_id,
                birth_date=related_child.birth_date,
                gender=related_child.gender,
                is_primary=link.is_primary,
                confirmed_observation_count=confirmed_observation_count(
                    s, related_child.id
                ),
            ))
        child_confirmed_count = (
            confirmed_observation_count(s, obs.child_id)
            if obs.child_id is not None
            else 0
        )

        return ObservationDetailResponse(
            **obs.model_dump(),
            observation_mode=run_context(latest_workflow_run(s, obs, "narrative")).get("mode"),
            narrative_context_changed=narrative_context_changed(s, obs),
            suggestions_ready=suggestions_current(s, obs),
            suggestions_stale=bool(latest_workflow_run(s, obs, "indicator_suggestion")) and not suggestions_current(s, obs),
            child_name=child.name if child else None,
            classroom_name=room.name if room else None,
            area_name=area.name if area else None,
            child_confirmed_count=child_confirmed_count,
            children=related_children,
            observer=observer,
            media=media,
            tags=tags,
        )


def export_observation_data(session: Session, obs: Observation) -> ExportObservation:
    """把数据库记录整理成与 DOCX 模板解耦的导出数据。"""
    area = session.get(Area, obs.area_id)
    observer = session.get(Teacher, obs.observer_id) if obs.observer_id else None
    links = session.exec(
        select(ObservationChild)
        .where(ObservationChild.observation_id == obs.id)
        .order_by(ObservationChild.is_primary.desc(), ObservationChild.child_id)
    ).all()
    export_children = []
    for link in links:
        child = session.get(Child, link.child_id)
        if not child:
            continue
        gender = child.gender.value if hasattr(child.gender, "value") else child.gender
        export_children.append(ExportChild(
            name=child.name,
            birth_date=child.birth_date,
            gender=gender,
        ))

    # 兼容尚未跑多人迁移的独立测试库；正式库以关联表为唯一多人来源。
    if not export_children and obs.child_id is not None:
        child = session.get(Child, obs.child_id)
        if child:
            gender = child.gender.value if hasattr(child.gender, "value") else child.gender
            export_children.append(ExportChild(
                name=child.name,
                birth_date=child.birth_date,
                gender=gender,
            ))

    tags = [tag for tag in current_observation_tags(session, obs) if tag.accepted is True]


    # 同一记录的照片会全部进入文档；视频各挑若干代表帧。
    highlight_frames: List[bytes] = []
    media_items = session.exec(
        select(Media).where(Media.observation_id == obs.id).order_by(Media.id)
    ).all()
    for media in media_items:
        media_path = UPLOAD_DIR / media.stored_filename
        if not media_path.is_file():
            continue
        if media.content_type.startswith("image/"):
            photo = prepare_export_photo(media_path)
            if photo:
                highlight_frames.append(photo)
        elif media.content_type.startswith("video/"):
            highlight_frames.extend(extract_highlight_frames(media_path))

    return ExportObservation(
        observation_id=obs.id,
        observed_at=obs.observed_at,
        age_group=obs.age_group,
        area_name=area.name if area else "",
        observer_name=observer.name if observer else "",
        children=export_children,
        location=obs.location,
        background_note=obs.background_note,
        purpose=obs.purpose,
        narrative=obs.narrative,
        analysis=obs.analysis,
        strategy=obs.strategy,
        indicators=[
            ExportIndicator(
                code=tag.indicator_code,
                name=tag.indicator_name,
                level=tag.level,
                level_desc=level_desc(tag.indicator_code, tag.level),
                evidence=(tag.ai_reason or "") if tag.source != "teacher_added" else "",
            )
            for tag in tags
        ],
        highlight_frames=highlight_frames,
    )


def safe_filename_part(value: str) -> str:
    """去掉系统文件名禁用字符，同时保留中文可读性。"""
    return "".join("_" if char in '\\/:*?\"<>|' else char for char in value).strip() or "未填写"


EXPORT_FORMATS = {
    "docx": (DOCX_MEDIA_TYPE, build_observation_document),
    "pdf": (PDF_MEDIA_TYPE, build_observation_pdf),
}


def validate_export_format(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in EXPORT_FORMATS:
        raise HTTPException(422, "导出格式只支持 docx、pdf")
    return normalized


def export_download(content: bytes, filename: str, media_type: str, extension: str):
    encoded = quote(filename)
    headers = {
        "Content-Disposition": (
            f'attachment; filename="observation.{extension}"; filename*=UTF-8\'\'{encoded}'
        ),
        "Content-Length": str(len(content)),
    }
    return StreamingResponse(BytesIO(content), media_type=media_type, headers=headers)


def build_export(records: List[ExportObservation], export_format: str, include_indicators: bool):
    media_type, builder = EXPORT_FORMATS[export_format]
    try:
        content = builder(records, include_indicators=include_indicators)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return content, media_type


@app.get("/observations/{obs_id}/export", tags=["5·成果"])
def export_observation(
    obs_id: int,
    request: Request,
    include_indicators: bool = Query(False, description="是否在观察分析末尾附带已采纳指标"),
    export_format: str = Query("docx", alias="format", description="docx / pdf"),
    authorization: Optional[str] = Header(None),
):
    """导出一条已确认观察记录；缺省保持 Word 行为。"""
    export_format = validate_export_format(export_format)
    with Session(engine) as s:
        account, teacher = authenticated_teacher(s, request, authorization)
        account_id = account.id
        obs = owned_observation(s, teacher, obs_id)
        if obs.status != "confirmed":
            raise HTTPException(400, "未确认的记录不能导出")
        require_analysis_and_strategy(obs)
        record = export_observation_data(s, obs)

    local = kindergarten_datetime(record.observed_at)
    names = safe_filename_part(child_names(record) or "未指定幼儿")
    filename = f"{names}_观察记录_{local:%Y%m%d}.{export_format}"
    content, media_type = build_export([record], export_format, include_indicators)
    with Session(engine) as s:
        s.add(ExportRecord(
            account_id=account_id,
            observation_id=obs_id,
            scope="single",
            format=export_format,
            file_name=filename,
            size=len(content),
            child_name=child_names(record) or None,
        ))
        s.commit()
    return export_download(content, filename, media_type, export_format)


@app.get("/exports/monthly", tags=["5·成果"])
def export_monthly_observations(
    request: Request,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    include_indicators: bool = Query(False, description="是否在观察分析末尾附带已采纳指标"),
    export_format: str = Query("docx", alias="format", description="docx / pdf"),
    authorization: Optional[str] = Header(None),
):
    """导出指定北京时间月份内的全部已确认观察记录。"""
    export_format = validate_export_format(export_format)
    with Session(engine) as s:
        account, teacher = authenticated_teacher(s, request, authorization)
        account_id = account.id
        confirmed = s.exec(
            select(Observation).where(
                Observation.status == "confirmed",
                Observation.observer_id == teacher.id,
                Observation.classroom_id == teacher.classroom_id,
            )
        ).all()
        selected = [
            obs for obs in confirmed
            if (
                kindergarten_datetime(obs.observed_at).year == year
                and kindergarten_datetime(obs.observed_at).month == month
            )
        ]
        selected.sort(key=lambda obs: kindergarten_datetime(obs.observed_at))
        if not selected:
            raise HTTPException(404, f"{year}年{month}月没有已确认的观察记录")
        for obs in selected:
            require_analysis_and_strategy(obs)
        records = [export_observation_data(s, obs) for obs in selected]

    observer_name = safe_filename_part(records[0].observer_name or "未填写")
    filename = f"自主游戏观察记录_{year}年{month}月_{observer_name}.{export_format}"
    content, media_type = build_export(records, export_format, include_indicators)
    with Session(engine) as s:
        s.add(ExportRecord(
            account_id=account_id,
            observation_id=None,
            scope="monthly",
            format=export_format,
            file_name=filename,
            size=len(content),
            child_name=None,
        ))
        s.commit()
    return export_download(content, filename, media_type, export_format)


@app.get(
    "/exports/history",
    response_model=List[ExportHistoryResponse],
    tags=["5·成果"],
)
def export_history(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    with Session(engine) as session:
        account, _ = authenticated_account(session, request, authorization)
        records = session.exec(
            select(ExportRecord)
            .where(ExportRecord.account_id == account.id)
            .order_by(ExportRecord.created_at.desc(), ExportRecord.id.desc())
        ).all()
        return [
            ExportHistoryResponse(
                id=item.id,
                observation_id=item.observation_id,
                scope=item.scope,
                format=item.format,
                file_name=item.file_name,
                size=item.size,
                child_name=item.child_name,
                created_at=item.created_at,
                # 首期不重复保存生成文件，页面会引导重新导出。
                download_url=None,
            )
            for item in records
        ]


@app.get("/metrics/ai-quality", tags=["5·成果"])
def ai_quality(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    AI 效果指标 —— 本项目最核心的三个数字，全部来自 observationtag 表。

      采纳率 = AI 建议且被采纳 ÷ AI 建议中教师已处理的
      漏检率 = 教师自己补的 ÷ 全部已采纳的
      分维度采纳率 = AI 在哪些维度准、哪些不准 → 下一轮优化方向
    """
    with Session(engine) as s:
        _, teacher = authenticated_teacher(s, request, authorization)
        observation_ids = select(Observation.id).where(
            Observation.observer_id == teacher.id,
            Observation.classroom_id == teacher.classroom_id,
        )
        tags = s.exec(
            select(ObservationTag).where(
                ObservationTag.observation_id.in_(observation_ids)
            )
        ).all()
        runs = s.exec(
            select(AIRun).where(AIRun.observation_id.in_(observation_ids))
        ).all()

    def quality_summary(group_tags):
        ai_tags = [t for t in group_tags if t.source == "ai_suggested"]
        resolved = [t for t in ai_tags if t.accepted is not None]
        accepted = [t for t in resolved if t.accepted]
        teacher_added = [t for t in group_tags if t.source == "teacher_added"]
        all_accepted = [
            t for t in group_tags
            if t.source in {"ai_suggested", "teacher_added"} and t.accepted is True
        ]

        by_dim = {}
        for tag in resolved:
            dim = INDICATORS.get(tag.indicator_code, {}).get("dimension", "未知")
            dimension = by_dim.setdefault(dim, {"已处理": 0, "采纳": 0})
            dimension["已处理"] += 1
            if tag.accepted:
                dimension["采纳"] += 1
        for dimension in by_dim.values():
            dimension["采纳率"] = (
                round(dimension["采纳"] / dimension["已处理"], 3)
                if dimension["已处理"] else None
            )

        return {
            "AI建议总数": len(ai_tags),
            "教师已处理": len(resolved),
            "教师采纳": len(accepted),
            "采纳率": round(len(accepted) / len(resolved), 3) if resolved else None,
            "教师自己补的": len(teacher_added),
            "漏检率": (
                round(len(teacher_added) / len(all_accepted), 3)
                if all_accepted else None
            ),
            "分维度采纳率": by_dim,
        }

    run_by_id = {run.id: run for run in runs}

    def version_for_run_id(run_id):
        if run_id is None:
            return "rule-mock-v1"
        run = run_by_id.get(run_id)
        return run.prompt_version if run else "unknown-ai-run"

    observation_versions = {}
    for tag in tags:
        if tag.source != "ai_suggested":
            continue
        observation_versions.setdefault(tag.observation_id, set()).add(
            version_for_run_id(tag.ai_run_id)
        )

    def version_for_tag(tag):
        if tag.ai_run_id is not None:
            return version_for_run_id(tag.ai_run_id)
        if tag.source == "teacher_added":
            versions = observation_versions.get(tag.observation_id, set())
            if len(versions) == 1:
                return next(iter(versions))
        return "rule-mock-v1"

    grouped_tags = {}
    for tag in tags:
        if tag.source not in {"ai_suggested", "teacher_added"}:
            continue
        grouped_tags.setdefault(version_for_tag(tag), []).append(tag)

    grouped_runs = {}
    for run in runs:
        grouped_runs.setdefault(run.prompt_version, []).append(run)

    versions = set(grouped_tags) | set(grouped_runs)
    version_details = {}
    for version in sorted(versions):
        version_runs = grouped_runs.get(version, [])
        if version == "rule-mock-v1":
            provider = "mock"
            model = "demo-mock-rule-v1"
            temperature = None
        else:
            providers = {run.provider for run in version_runs}
            models = {run.model for run in version_runs}
            temperatures = {
                run.temperature for run in version_runs if run.temperature is not None
            }
            provider = next(iter(providers)) if len(providers) == 1 else "mixed"
            model = next(iter(models)) if len(models) == 1 else "mixed"
            temperature = (
                next(iter(temperatures)) if len(temperatures) == 1
                else "mixed" if temperatures else None
            )

        latency_values = [
            run.latency_ms for run in version_runs if run.latency_ms is not None
        ]
        token_values = [
            run.token_usage.get("total_tokens")
            for run in version_runs
            if isinstance(run.token_usage, dict)
            and isinstance(run.token_usage.get("total_tokens"), (int, float))
        ]
        detail = {
            "provider": provider,
            "model": model,
            "temperature": temperature,
            **quality_summary(grouped_tags.get(version, [])),
            "调用统计": {
                "平均latency_ms": (
                    round(sum(latency_values) / len(latency_values), 1)
                    if latency_values else None
                ),
                "平均token消耗": (
                    round(sum(token_values) / len(token_values), 1)
                    if token_values else None
                ),
                "总调用次数": len(version_runs),
                "失败次数": sum(run.status == "failed" for run in version_runs),
            },
        }
        version_details[version] = detail

    return {
        **quality_summary(tags),
        "按prompt_version": version_details,
        "说明": "指标可能混合 mock 与真实模型结果；可通过 ai_run 区分模型、prompt 版本与参数。",
    }
