"""
帮帮师记 API

演示闭环：
  上传素材 → 建观察记录 → 绑定素材 → AI 生成客观白描
  → AI 推荐候选指标 → 教师采纳/否掉/自己加 → 教师补分析和措施 → 定稿 → 查看完整记录
  → 查看 AI 候选采纳率

【当前 AI 部分为 DEMO MOCK】所有 mock 返回都带 is_mock=True 和 notice 提示。
"""

from pathlib import Path
from uuid import uuid4
from datetime import datetime
from typing import Optional, List, Literal

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, select

from models import (
    engine, Area, ClassRoom, Child,
    Observation, Media, ObservationTag,
)
from indicators import INDICATORS, all_indicators_flat, level_desc
import ai_service

app = FastAPI(
    title="帮帮师记 API",
    version="0.2",
    description="幼儿园教师素材沉淀与观察记录生成。AI 部分当前为演示 mock。",
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "video/mp4": ".mp4",
}
MAX_SIZE = 20 * 1024 * 1024  # 20MB


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
    """教师修改观察记录的文字部分"""
    purpose: Optional[str] = None
    narrative: Optional[str] = None
    analysis: Optional[str] = None
    strategy: Optional[str] = None


class ObservationCreate(BaseModel):
    """新建观察记录。状态与阶段时间戳只由后端维护。"""
    model_config = ConfigDict(extra="forbid")

    child_id: int
    area_id: int
    age_group: str
    media_type: str
    observed_at: Optional[datetime] = None
    purpose: Optional[str] = None


ObservationStatus = Literal[
    "uploaded",
    "processing",
    "ready_for_review",
    "confirmed",
    "failed",
]

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
    now = datetime.now()
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

@app.post("/uploads", status_code=201, tags=["1·素材"])
async def upload_media(
    file: UploadFile = File(...),
    duration_sec: Optional[int] = Query(
        None, description="视频时长（秒）。指标 1.1 的层级分界靠它纯计算得出，零幻觉。照片可不填。"
    ),
):
    """上传一份模拟照片或视频，同时在 media 表登记一条"""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "只支持 JPG、PNG 和 MP4 文件")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(413, "文件不能超过 20MB")

    ext = ALLOWED_TYPES[file.content_type]
    stored_filename = f"{uuid4().hex}{ext}"
    (UPLOAD_DIR / stored_filename).write_bytes(content)

    with Session(engine) as s:
        media = Media(
            stored_filename=stored_filename,
            content_type=file.content_type,
            size=len(content),
            duration_sec=duration_sec,
        )
        s.add(media)
        s.commit()
        s.refresh(media)
        return media


@app.get("/media", tags=["1·素材"])
def list_media():
    """所有已上传的素材"""
    with Session(engine) as s:
        return s.exec(select(Media)).all()


# ============================================================
# 2. 观察记录
# ============================================================

@app.post("/observations", status_code=201, tags=["2·观察记录"])
def create_observation(payload: ObservationCreate):
    """新建观察记录；状态固定由后端初始化为 uploaded。"""
    with Session(engine) as s:
        # 自动补班级：从幼儿身上带出来，教师不用填
        child = s.get(Child, payload.child_id)
        if not child:
            raise HTTPException(404, f"找不到 id={payload.child_id} 的幼儿")
        observation = Observation(
            child_id=payload.child_id,
            area_id=payload.area_id,
            classroom_id=child.classroom_id,
            observed_at=payload.observed_at or datetime.now(),
            age_group=payload.age_group,
            media_type=payload.media_type,
            purpose=payload.purpose,
            status="uploaded",
        )
        s.add(observation)
        s.commit()
        s.refresh(observation)
        return observation


@app.get("/observations", tags=["2·观察记录"])
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
        obs.media_type = "video" if media.content_type == "video/mp4" else "photo"
        s.add(media)
        s.add(obs)
        s.commit()
        return {"ok": True, "observation_id": obs_id, "media_id": media_id,
                "media_type": obs.media_type, "status": obs.status}


@app.patch("/observations/{obs_id}", tags=["2·观察记录"])
def update_observation(obs_id: int, payload: ObservationUpdate):
    """教师修改观察目的 / 白描 / 分析 / 措施"""
    with Session(engine) as s:
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")

        data = payload.model_dump(exclude_unset=True)

        # 教师动过 AI 白描 → 来源自动从 ai 变成 ai_edited
        if "narrative" in data and obs.narrative_source == "ai":
            if data["narrative"] != obs.narrative:
                obs.narrative_source = "ai_edited"

        for k, v in data.items():
            setattr(obs, k, v)

        s.add(obs)
        s.commit()
        s.refresh(obs)
        return obs


@app.post("/observations/{obs_id}/confirm", tags=["2·观察记录"])
def confirm_observation(obs_id: int):
    """教师定稿。要求白描和至少一个已采纳的指标都到位。"""
    with Session(engine) as s:
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")
        ensure_status_transition(obs, "confirmed")
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

@app.post("/observations/{obs_id}/narrative", tags=["3·AI（mock）"])
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
        s.add(obs)
        s.commit()
        s.refresh(obs)

        return {
            "observation_id": obs_id,
            "status": obs.status,
            "processing_started_at": obs.processing_started_at,
            "narrative": result["narrative"],
            "is_mock": result["is_mock"],
            "engine": result["engine"],
            "notice": result["notice"],
        }


@app.post("/observations/{obs_id}/suggest-tags", tags=["3·AI（mock）"])
def suggest_tags(obs_id: int):
    """
    【AI 工作流 B】根据白描 + 区域 + 年龄段，推荐 2-3 个候选指标。

    候选会立刻落库为 source=ai_suggested、accepted=None（未处理），
    等教师逐条采纳或否掉。这是「AI 候选采纳率」能被统计的前提。
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
        elif obs.status != "processing":
            ensure_status_transition(obs, "ready_for_review")

        area = s.get(Area, obs.area_id)
        media = s.exec(select(Media).where(Media.observation_id == obs_id)).first()

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

        saved = []
        for sug in result["suggestions"]:
            tag = ObservationTag(
                observation_id=obs_id,
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
                "rank": tag.rank_in_suggestion,
            })

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
            "quant_hits": result["quant_hits"],
            "is_mock": result["is_mock"],
            "engine": result["engine"],
            "notice": result["notice"],
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
    教师采纳或否掉一条 AI 候选。
    这一下写入的 accepted 字段，就是「AI 候选采纳率」的数据来源。
    """
    with Session(engine) as s:
        tag = s.get(ObservationTag, tag_id)
        if not tag or tag.observation_id != obs_id:
            raise HTTPException(404, "标注不存在")

        tag.accepted = decision.accepted
        tag.resolved_at = datetime.now()
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

        tag = ObservationTag(
            observation_id=obs_id,
            indicator_code=payload.indicator_code,
            indicator_name=item["name"],
            level=payload.level,
            source="teacher_added",
            accepted=True,          # 教师自己加的，默认就是采纳
            resolved_at=datetime.now(),
        )
        s.add(tag)
        s.commit()
        s.refresh(tag)
        return tag


# ============================================================
# 5. 完整记录 & 指标
# ============================================================

@app.get("/observations/{obs_id}", tags=["5·成果"])
def get_observation_detail(obs_id: int):
    """一条观察记录的完整内容：四段正文 + 素材 + 已采纳的指标"""
    with Session(engine) as s:
        obs = s.get(Observation, obs_id)
        if not obs:
            raise HTTPException(404, "观察记录不存在")

        child = s.get(Child, obs.child_id)
        area = s.get(Area, obs.area_id)
        room = s.get(ClassRoom, obs.classroom_id) if obs.classroom_id else None
        media = s.exec(select(Media).where(Media.observation_id == obs_id)).all()
        tags = s.exec(
            select(ObservationTag).where(ObservationTag.observation_id == obs_id)
        ).all()

        return {
            "id": obs.id,
            "状态": {
                "uploaded": "已上传",
                "processing": "AI 处理中",
                "ready_for_review": "待教师确认",
                "confirmed": "已确认",
                "failed": "AI 处理失败",
            }.get(obs.status, obs.status),
            "观察对象": child.name if child else None,
            "班级": room.name if room else None,
            "年龄段": {"small": "小班", "middle": "中班", "large": "大班"}.get(obs.age_group, obs.age_group),
            "观察地点": area.name if area else None,
            "观察时间": obs.observed_at,
            "观察目的": obs.purpose,
            "观察描述": obs.narrative,
            "白描来源": {"ai": "AI 生成", "ai_edited": "AI 生成后教师修改", "manual": "教师手写"}.get(obs.narrative_source),
            "观察分析": obs.analysis,
            "措施": obs.strategy,
            "已采纳指标": [
                {
                    "编号": t.indicator_code,
                    "名称": t.indicator_name,
                    "层级": {1: "初阶", 2: "中阶", 3: "高阶"}[t.level],
                    "行为描述": level_desc(t.indicator_code, t.level),
                    "来源": "AI 建议" if t.source == "ai_suggested" else "教师补充",
                }
                for t in tags if t.accepted is True
            ],
            "素材": [{"文件名": m.stored_filename, "类型": m.content_type,
                     "时长秒": m.duration_sec} for m in media],
            "确认时间": obs.confirmed_at,
            "处理开始时间": obs.processing_started_at,
            "待确认时间": obs.ready_at,
            "失败原因": obs.failure_reason,
        }


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

    ai_tags = [t for t in tags if t.source == "ai_suggested"]
    resolved = [t for t in ai_tags if t.accepted is not None]
    accepted = [t for t in resolved if t.accepted]
    teacher_added = [t for t in tags if t.source == "teacher_added"]
    all_accepted = [t for t in tags if t.accepted is True]

    by_dim = {}
    for t in resolved:
        dim = INDICATORS.get(t.indicator_code, {}).get("dimension", "未知")
        d = by_dim.setdefault(dim, {"已处理": 0, "采纳": 0})
        d["已处理"] += 1
        if t.accepted:
            d["采纳"] += 1
    for d in by_dim.values():
        d["采纳率"] = round(d["采纳"] / d["已处理"], 3) if d["已处理"] else None

    return {
        "AI建议总数": len(ai_tags),
        "教师已处理": len(resolved),
        "教师采纳": len(accepted),
        "采纳率": round(len(accepted) / len(resolved), 3) if resolved else None,
        "教师自己补的": len(teacher_added),
        "漏检率": round(len(teacher_added) / len(all_accepted), 3) if all_accepted else None,
        "分维度采纳率": by_dim,
        "说明": "当前 AI 为 demo mock，这些数字只用于验证埋点链路是否通，不代表真实模型效果。",
    }
