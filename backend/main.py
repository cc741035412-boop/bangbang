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
import re
import secrets
import shutil
import subprocess
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Header, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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
)
from time_utils import utc_now
from export_service import (
    DOCX_MEDIA_TYPE,
    MARKDOWN_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    ExportChild,
    ExportIndicator,
    ExportObservation,
    build_observation_document,
    build_observation_markdown,
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
    format: Literal["docx", "pdf", "md"]
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


class ObservationDetailResponse(ObservationResponse):
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
    "ready_for_review": {"confirmed"},
    "confirmed": set(),
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
    children.sort(key=lambda child: (child.id not in primary_ids, child.id))
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


def _extract_video_frames(source: Path, count: int = 10) -> List[Dict]:
    """用 ffmpeg 从视频里按时间均匀抽几帧，返回 [{timestamp_sec, data_uri}]。

    依赖 imageio-ffmpeg（pip 自带 ffmpeg 二进制，无需系统安装）。
    - 在 0 ~ 时长 之间均匀采 count 个点（含首尾），帧间覆盖更充分；
    - 空白帧（纯黑/纯白/无内容）会在附近重采样，尽量覆盖有内容的画面；
    - 抽帧失败或不是合法视频时返回空列表（调用方降级到 mock）。
    """
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return []

    try:
        probe = subprocess.run(
            [exe, "-i", str(source)], capture_output=True, text=True, timeout=30
        )
        duration = None
        for line in probe.stderr.splitlines():
            if "Duration:" in line:
                m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", line)
                if m:
                    hours, minutes, seconds = m.group(1), m.group(2), m.group(3)
                    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                break
        if not duration or duration <= 0:
            return []

        if count <= 1:
            timestamps = [0.0]
        else:
            last = max(0.0, duration - 0.1)
            timestamps = [duration * i / (count - 1) for i in range(count)]
            timestamps[0] = 0.0
            timestamps[-1] = last

        frames: List[Dict] = []
        for t in timestamps:
            data_uri = _grab_frame(exe, source, t, duration)
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
    except Exception:
        return []


def _media_vision_frames(media: Media) -> Optional[List[Dict]]:
    """把素材转成"视觉模型可用的画面帧列表"，供豆包白描使用。

    - 图片：用原图（1 帧）。
    - 视频：用 ffmpeg 按时间均匀抽 10 帧，按时间顺序给模型。
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
    frames = _extract_video_frames(source, count=10)
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
    """使用 macOS 自带 Quick Look 抽取视频首帧；失败不影响素材保存。"""
    thumbnail_path = get_thumbnail_path(source_path.name)
    error_path = get_thumbnail_error_path(source_path.name)
    qlmanage = shutil.which("qlmanage")

    if not qlmanage:
        reason = "当前服务器没有可用的视频抽帧工具"
        error_path.write_text(reason, encoding="utf-8")
        return reason

    try:
        with tempfile.TemporaryDirectory(prefix="thumbnail-", dir=UPLOAD_DIR) as temp_dir:
            result = subprocess.run(
                [qlmanage, "-t", "-s", str(THUMBNAIL_SIZE), "-o", temp_dir, str(source_path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            generated_path = Path(temp_dir) / f"{source_path.name}.png"
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
        secure=RUNTIME_ENV in PRODUCTION_ENVS,
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
    """幼儿列表。

    带登录态时只返回当前教师班级的幼儿，与「新增/删除幼儿只能作用于本班」保持一致；
    无登录态时（demo 脚本、未开启登录的旧流程）返回全部，便于演示兼容。
    """
    with Session(engine) as s:
        auth = authenticated_account(s, request, authorization, required=False)
        if auth is None:
            return s.exec(select(Child)).all()
        account, _ = auth
        teacher = s.get(Teacher, account.teacher_id)
        if not teacher:
            return []
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
            select(Observation).where(Observation.child_id == child.id)
        ).all()
        observations_by_id = {item.id: item for item in legacy_observations}
        if linked_ids:
            linked_observations = session.exec(
                select(Observation).where(Observation.id.in_(linked_ids))
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
def update_child(child_id: int, payload: ChildUpdate):
    """修改已有幼儿的姓名、出生日期或性别。"""
    with Session(engine) as s:
        child = s.get(Child, child_id)
        if not child:
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
def list_teachers():
    """所有教师；供极简设置页读取。"""
    with Session(engine) as s:
        return s.exec(select(Teacher)).all()


@app.patch("/teachers/{teacher_id}", response_model=TeacherResponse, tags=["基础"])
def update_teacher(teacher_id: int, payload: TeacherUpdate):
    """修改已有教师的姓名。"""
    with Session(engine) as s:
        teacher = s.get(Teacher, teacher_id)
        if not teacher:
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
    file: UploadFile = File(...),
    duration_sec: Optional[int] = Query(
        None, description="视频时长（秒）。指标 1.1 的层级分界靠它纯计算得出，零幻觉。照片可不填。"
    ),
):
    """上传一份模拟照片或视频，同时在 media 表登记一条"""
    content_type, ext = resolve_upload_type(file)
    stored_filename = f"{uuid4().hex}{ext}"
    stored_path = UPLOAD_DIR / stored_filename
    size = 0

    try:
        with stored_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_SIZE:
                    raise HTTPException(413, "文件不能超过 200MB")
                destination.write(chunk)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise

    # 视频：探测真实时长；超过建议上限（3 分钟）直接拒绝，避免拉低白描质量。并回填真实时长。
    real_duration_sec = duration_sec
    if content_type.startswith("video/"):
        probed = _probe_video_duration(stored_path)
        if probed is not None:
            real_duration_sec = int(round(probed))
        elif duration_sec is None:
            real_duration_sec = None
        if probed is not None and probed > MAX_DURATION_SEC:
            stored_path.unlink(missing_ok=True)
            raise HTTPException(
                422,
                "视频太长了，建议录 1~3 分钟的片段。超过 3 分钟会影响白描效果，请缩短后再上传。",
            )
        generate_video_thumbnail(stored_path)

    with Session(engine) as s:
        media = Media(
            stored_filename=stored_filename,
            content_type=content_type,
            size=size,
            duration_sec=real_duration_sec,
        )
        s.add(media)
        s.commit()
        s.refresh(media)
        return media_response(media)


@app.get("/media", response_model=List[MediaResponse], tags=["1·素材"])
def list_media():
    """所有已上传的素材"""
    with Session(engine) as s:
        return [media_response(media) for media in s.exec(select(Media)).all()]


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
def get_media_file(media_id: int):
    """读取一份已上传素材，供前端展示图片或视频首帧。"""
    with Session(engine) as s:
        media = s.get(Media, media_id)
        if not media:
            raise HTTPException(404, "素材不存在")

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
def get_media_thumbnail(media_id: int):
    """返回服务端生成的视频缩略图；历史视频首次读取时补生成。"""
    with Session(engine) as s:
        media = s.get(Media, media_id)
        if not media:
            raise HTTPException(404, "素材不存在")
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
        authenticated = authenticated_account(
            s, request, authorization, required=False,
        )
        teacher_id = authenticated[0].teacher_id if authenticated else DEFAULT_TEACHER_ID
        teacher = s.get(Teacher, teacher_id)
        if not teacher:
            raise HTTPException(500, "账号关联的教师信息不存在")
        if not authenticated and teacher.classroom_id != DEFAULT_CLASSROOM_ID:
            raise HTTPException(500, "默认教师与默认班级配置不一致")
        room = s.get(ClassRoom, teacher.classroom_id)
        if not room:
            raise HTTPException(500, "默认班级配置无效，请检查 DEFAULT_CLASSROOM_ID")
        if payload.child_id is not None and not s.get(Child, payload.child_id):
            raise HTTPException(404, f"找不到 id={payload.child_id} 的幼儿")
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
):
    """所有观察记录（简要），可按状态 / 幼儿 / 区域 / 观察日期区间组合过滤。"""
    if (
        date_from is not None
        and date_to is not None
        and date_from > date_to
    ):
        raise HTTPException(422, "date_from 不能晚于 date_to")
    with Session(engine) as s:
        if child_id is not None and s.get(Child, child_id) is None:
            raise HTTPException(404, f"找不到 id={child_id} 的幼儿")
        if area_id is not None and s.get(Area, area_id) is None:
            raise HTTPException(404, f"找不到 id={area_id} 的游戏区域")

        statement = select(Observation)
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
        if date_from is not None or date_to is not None:
            start, end_exclusive = observed_at_day_bounds(date_from, date_to)
            if start is not None:
                statement = statement.where(Observation.observed_at >= start)
            if end_exclusive is not None:
                statement = statement.where(Observation.observed_at < end_exclusive)
        return s.exec(statement).all()


@app.post("/observations/{obs_id}/attach-media", tags=["2·观察记录"])
def attach_media(obs_id: int, media_id: int = Query(..., description="要绑定的素材 id")):
    """把已上传的素材绑定到这条观察记录上"""
    with Session(engine) as s:
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")
        media = s.get(Media, media_id)
        if not media:
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

        media.observation_id = obs_id
        if obs.media_type is None:
            if media.content_type.startswith("image/"):
                obs.media_type = "image"
            elif media.content_type.startswith("video/"):
                obs.media_type = "video"
        s.add(media)
        s.add(obs)
        s.commit()
        return {"ok": True, "observation_id": obs_id, "media_id": media_id,
                "media_type": obs.media_type, "status": obs.status}


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
        account, _ = authenticated_account(session, request, authorization)
        teacher = session.get(Teacher, account.teacher_id)
        observation = session.get(Observation, obs_id)
        if (
            not teacher
            or not observation
            or observation.classroom_id != teacher.classroom_id
        ):
            raise HTTPException(404, "观察记录不存在")
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
def update_observation(obs_id: int, payload: ObservationUpdate):
    """教师补幼儿和现场说明，或修改观察目的 / 白描 / 分析 / 措施。"""
    with Session(engine) as s:
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")

        data = payload.model_dump(exclude_unset=True)

        context_fields = {"child_id", "note"} & data.keys()
        if context_fields and obs.status not in {"uploaded", "ready_for_review"}:
            raise HTTPException(
                400,
                detail={
                    "message": f"状态为 {obs.status} 时不能更新 child_id 或 note",
                    "current_status": obs.status,
                },
            )
        if "child_id" in data and data["child_id"] is not None:
            if not s.get(Child, data["child_id"]):
                raise HTTPException(404, f"找不到 id={data['child_id']} 的幼儿")

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


@app.post("/observations/{obs_id}/confirm", tags=["2·观察记录"])
def confirm_observation(obs_id: int):
    """教师定稿。要求幼儿、白描和至少一个已采纳的指标都到位。"""
    with Session(engine) as s:
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")
        ensure_status_transition(obs, "confirmed")
        if obs.child_id is None:
            raise HTTPException(400, "请先选择这条记录关于哪位幼儿")
        if not obs.narrative:
            raise HTTPException(400, "还没有白描，不能定稿")

        accepted = s.exec(
            select(ObservationTag).where(
                ObservationTag.observation_id == obs_id,
                ObservationTag.accepted == True,  # noqa: E712
            )
        ).all()
        if not accepted:
            raise HTTPException(400, "还没有任何已采纳的指标，不能定稿")

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
        account, _ = authenticated_account(s, request, authorization)
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")

        # 说明：观察记录列表本身不按班级隔离（演示环境所有记录可见），
        # 因此删除也不按班级拦截，方便教师清理导入的测试记录。
        # 观察记录删除属于"整条记录清理"，不做级联 / 二次确认的额外参数。
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
def generate_narrative(obs_id: int):
    """
    【AI 工作流 A】根据绑定的素材生成客观白描。
    结果写入 narrative + narrative_ai_raw，来源标记为 ai。
    """
    with Session(engine) as s:
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")

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
                asr = asr_service.transcribe_video(media_path)
                if asr and not asr.get("is_mock"):
                    transcript = asr.get("transcript")

        # 观察对象幼儿数量（老师选择的），决定白描描写哪几位主体；未选时默认 1。
        child_count_hint = len(s.exec(
            select(ObservationChild).where(ObservationChild.observation_id == obs_id)
        ).all()) or 1

        try:
            result = ai_service.generate_narrative(
                area_code=area.code if area else "",
                area_name=area.name if area else None,
                media_type=obs.media_type,
                duration_sec=media.duration_sec,
                frames=vision_frames,
                transcript=transcript,
                child_count_hint=child_count_hint,
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
        if result.get("ai_run"):
            s.add(AIRun(observation_id=obs_id, **result["ai_run"]))
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


@app.post("/observations/{obs_id}/suggest-tags", tags=["3·AI"])
def suggest_tags(obs_id: int):
    """
    【AI 工作流 B】根据白描 + 区域 + 年龄段，推荐 2-3 个候选指标。

    系统判定与 AI 建议分别落库：
    - quant_hits → source=system_determined、accepted=True（默认选中）
    - suggestions → source=ai_suggested、accepted=None（等待教师决定）
    """
    with Session(engine) as s:
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")
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

        existing_candidates = s.exec(
            select(ObservationTag).where(
                ObservationTag.observation_id == obs_id,
                ObservationTag.source.in_({"system_determined", "ai_suggested"}),
            )
        ).all()
        if existing_candidates:
            system_tags = [t for t in existing_candidates if t.source == "system_determined"]
            ai_tags = [t for t in existing_candidates if t.source == "ai_suggested"]
            linked_run = next(
                (s.get(AIRun, tag.ai_run_id) for tag in existing_candidates if tag.ai_run_id),
                None,
            )
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

        # 同一条记录重复调用时，先清掉上一轮还没处理的 AI 候选
        old = s.exec(
            select(ObservationTag).where(
                ObservationTag.observation_id == obs_id,
                ObservationTag.source == "ai_suggested",
                ObservationTag.accepted == None,  # noqa: E711
            )
        ).all()
        for t in old:
            s.delete(t)
        s.commit()

        try:
            result = ai_service.suggest_indicators(
                narrative=obs.narrative,
                area_code=area.code if area else "",
                area_name=area.name if area else "",
                age_group=obs.age_group,
                duration_sec=media.duration_sec if media else None,
                child_names=classroom_child_names_for_anonymization(s, obs),
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


# ============================================================
# 4. 教师确认环节
# ============================================================

@app.get("/observations/{obs_id}/tags", tags=["4·教师确认"])
def list_tags(obs_id: int):
    """这条记录上所有指标标注"""
    with Session(engine) as s:
        return s.exec(
            select(ObservationTag).where(ObservationTag.observation_id == obs_id)
        ).all()


@app.patch("/observations/{obs_id}/tags/{tag_id}", tags=["4·教师确认"])
def decide_tag(obs_id: int, tag_id: int, decision: TagDecision):
    """
    教师采纳或否掉一条 AI 候选，或取消 / 恢复一条系统判定。
    AI 建议的 accepted 字段是「AI 候选采纳率」的数据来源。
    """
    with Session(engine) as s:
        tag = s.get(ObservationTag, tag_id)
        if not tag or tag.observation_id != obs_id:
            raise HTTPException(404, "标注不存在")

        tag.accepted = decision.accepted
        tag.resolved_at = utc_now()
        s.add(tag)
        s.commit()
        s.refresh(tag)
        return {"ok": True, "tag": tag,
                "note": "采纳" if decision.accepted else "已否掉"}


@app.post("/observations/{obs_id}/tags", status_code=201, tags=["4·教师确认"])
def add_tag_by_teacher(obs_id: int, payload: TagCreate):
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
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")

        latest_candidate = s.exec(
            select(ObservationTag).where(
                ObservationTag.observation_id == obs_id,
                ObservationTag.ai_run_id != None,  # noqa: E711
                ObservationTag.source.in_({"ai_suggested", "system_determined"}),
            ).order_by(ObservationTag.id.desc())
        ).first()

        tag = ObservationTag(
            observation_id=obs_id,
            ai_run_id=latest_candidate.ai_run_id if latest_candidate else None,
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
def get_observation_detail(obs_id: int):
    """一条观察记录的完整内容：四段正文 + 素材 + 已采纳的指标"""
    with Session(engine) as s:
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")

        child = s.get(Child, obs.child_id) if obs.child_id is not None else None
        observer = s.get(Teacher, obs.observer_id) if obs.observer_id is not None else None
        area = s.get(Area, obs.area_id)
        room = s.get(ClassRoom, obs.classroom_id) if obs.classroom_id else None
        media = s.exec(select(Media).where(Media.observation_id == obs_id)).all()
        tags = s.exec(
            select(ObservationTag).where(ObservationTag.observation_id == obs_id)
        ).all()
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

    tags = session.exec(
        select(ObservationTag)
        .where(
            ObservationTag.observation_id == obs.id,
            ObservationTag.accepted == True,  # noqa: E712
            ObservationTag.source.in_({
                "system_determined",
                "ai_suggested",
                "teacher_added",
            }),
        )
        .order_by(ObservationTag.id)
    ).all()
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
            ExportIndicator(code=tag.indicator_code, name=tag.indicator_name, level=tag.level)
            for tag in tags
        ],
    )


def safe_filename_part(value: str) -> str:
    """去掉系统文件名禁用字符，同时保留中文可读性。"""
    return "".join("_" if char in '\\/:*?\"<>|' else char for char in value).strip() or "未填写"


EXPORT_FORMATS = {
    "docx": (DOCX_MEDIA_TYPE, build_observation_document),
    "pdf": (PDF_MEDIA_TYPE, build_observation_pdf),
    "md": (MARKDOWN_MEDIA_TYPE, build_observation_markdown),
}


def validate_export_format(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in EXPORT_FORMATS:
        raise HTTPException(422, "导出格式只支持 docx、pdf 或 md")
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
    export_format: str = Query("docx", alias="format", description="docx / pdf / md"),
    authorization: Optional[str] = Header(None),
):
    """导出一条已确认观察记录；缺省保持 Word 行为。"""
    export_format = validate_export_format(export_format)
    with Session(engine) as s:
        authenticated = authenticated_account(s, request, authorization, required=False)
        account_id = authenticated[0].id if authenticated else None
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")
        if obs.status != "confirmed":
            raise HTTPException(400, "未确认的记录不能导出")
        record = export_observation_data(s, obs)

    local = kindergarten_datetime(record.observed_at)
    names = safe_filename_part(child_names(record) or "未指定幼儿")
    filename = f"{names}_观察记录_{local:%Y%m%d}.{export_format}"
    content, media_type = build_export([record], export_format, include_indicators)
    if account_id is not None:
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
    export_format: str = Query("docx", alias="format", description="docx / pdf / md"),
    authorization: Optional[str] = Header(None),
):
    """导出指定北京时间月份内的全部已确认观察记录。"""
    export_format = validate_export_format(export_format)
    with Session(engine) as s:
        authenticated = authenticated_account(s, request, authorization, required=False)
        account_id = authenticated[0].id if authenticated else None
        confirmed = s.exec(
            select(Observation).where(Observation.status == "confirmed")
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
        records = [export_observation_data(s, obs) for obs in selected]

    observer_name = safe_filename_part(records[0].observer_name or "未填写")
    filename = f"自主游戏观察记录_{year}年{month}月_{observer_name}.{export_format}"
    content, media_type = build_export(records, export_format, include_indicators)
    if account_id is not None:
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
def ai_quality():
    """
    AI 效果指标 —— 本项目最核心的三个数字，全部来自 observationtag 表。

      采纳率 = AI 建议且被采纳 ÷ AI 建议中教师已处理的
      漏检率 = 教师自己补的 ÷ 全部已采纳的
      分维度采纳率 = AI 在哪些维度准、哪些不准 → 下一轮优化方向
    """
    with Session(engine) as s:
        tags = s.exec(select(ObservationTag)).all()
        runs = s.exec(select(AIRun)).all()

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
