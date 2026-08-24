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
from datetime import date, datetime
from typing import Optional, List, Literal
import shutil
import subprocess
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlmodel import Session, select

from models import (
    engine, Area, ClassRoom, Child, Teacher,
    Observation, ObservationChild, Media, AIRun, ObservationTag,
)
from indicators import INDICATORS, all_indicators_flat, level_desc
from config import DEFAULT_CLASSROOM_ID, DEFAULT_TEACHER_ID, UPLOAD_DIR
from time_utils import utc_now
import ai_service

app = FastAPI(
    title="帮帮师记 API",
    version="0.2",
    description="幼儿园教师素材沉淀与观察记录生成。工作流 B 支持 mock / DeepSeek 切换。",
)

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
# 基础
# ============================================================

@app.get("/health", tags=["基础"])
def health():
    return {"status": "ok"}


@app.get("/areas", tags=["基础"])
def list_areas():
    """所有游戏区域"""
    with Session(engine) as s:
        return s.exec(select(Area)).all()


@app.get("/children", tags=["基础"])
def list_children():
    """所有小朋友"""
    with Session(engine) as s:
        return s.exec(select(Child)).all()


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

    if content_type.startswith("video/"):
        generate_video_thumbnail(stored_path)

    with Session(engine) as s:
        media = Media(
            stored_filename=stored_filename,
            content_type=content_type,
            size=size,
            duration_sec=duration_sec,
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
def create_observation(payload: ObservationCreate):
    """现场新建观察记录；只要求游戏区，状态固定为 uploaded。"""
    with Session(engine) as s:
        teacher = s.get(Teacher, DEFAULT_TEACHER_ID)
        if not teacher:
            raise HTTPException(500, "默认教师配置无效，请检查 DEFAULT_TEACHER_ID")
        if teacher.classroom_id != DEFAULT_CLASSROOM_ID:
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


@app.get(
    "/observations",
    response_model=List[ObservationResponse],
    tags=["2·观察记录"],
)
def list_observations(
    status: Optional[ObservationStatus] = Query(None, description="按处理状态过滤"),
):
    """所有观察记录（简要），可按状态过滤。"""
    with Session(engine) as s:
        statement = select(Observation)
        if status is not None:
            statement = statement.where(Observation.status == status)
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

        try:
            result = ai_service.generate_narrative(
                area_code=area.code if area else "",
                media_type=obs.media_type,
                duration_sec=media.duration_sec,
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
