from typing import Dict, Optional
from datetime import datetime
from sqlalchemy import Column, JSON
from sqlmodel import SQLModel, Field, create_engine
from config import DATABASE_PATH
from time_utils import UTCDateTime, utc_now


# ========== 表1：游戏区域 ==========
class Area(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str    # 英文代号，程序用，如 construction
    name: str    # 中文名，人看，如 建构区


# ========== 表2：班级 ==========
class ClassRoom(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str         # 班级名，如 中二班
    age_group: str    # small=小班 / middle=中班 / large=大班


# ========== 表3：幼儿 ==========
class Child(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    classroom_id: int = Field(foreign_key="classroom.id")


# ========== 表4：观察记录 ==========
class Observation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    child_id: Optional[int] = Field(default=None, foreign_key="child.id")
    area_id: int = Field(foreign_key="area.id")
    classroom_id: Optional[int] = Field(default=None, foreign_key="classroom.id")

    observed_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(UTCDateTime(), nullable=False),
    )
    age_group: str      # 快照：拍摄当时的年龄段。孩子会升班，历史记录的判定依据不能跟着变
    media_type: Optional[str] = None  # image / video；绑定首个素材时由 MIME 推断

    # ---- 一份完整观察记录的四段，格式来自真实教研文书 ----
    purpose: Optional[str] = None      # ① 观察目的（教师拍摄前就预设好的）
    note: Optional[str] = None         # 现场一句话补充，教师可稍后修改
    narrative: Optional[str] = None    # ② 客观白描
    analysis: Optional[str] = None     # ③ 观察分析（教师主笔）
    strategy: Optional[str] = None     # ④ 措施（教师主笔，AI 最做不好的一栏）

    # 白描的来源，以及 AI 的原始版本
    narrative_source: Optional[str] = None    # ai / ai_edited / manual
    narrative_ai_raw: Optional[str] = None    # 留着对比教师改了多少

    # uploaded → processing → ready_for_review → confirmed
    #                       ↘ failed → processing（重试）
    status: str = "uploaded"
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(UTCDateTime(), nullable=False),
    )
    processing_started_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime(), nullable=True),
    )
    ready_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime(), nullable=True),
    )
    confirmed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime(), nullable=True),
    )
    failure_reason: Optional[str] = None


# ========== 表5：素材 ==========
class Media(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    stored_filename: str                  # uploads/ 里的真实文件名
    content_type: str                     # 规范化 MIME，如 image/heic、video/quicktime
    size: int                             # 字节数
    duration_sec: Optional[int] = None    # 视频时长，指标 1.1 的层级分界靠它算，纯计算零幻觉
    observation_id: Optional[int] = Field(default=None, foreign_key="observation.id")
    uploaded_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(UTCDateTime(), nullable=False),
    )


# ========== 表6：AI 调用记录 ==========
class AIRun(SQLModel, table=True):
    """一次 AI 工作流调用的完整审计记录。"""

    __tablename__ = "ai_run"

    id: Optional[int] = Field(default=None, primary_key=True)
    observation_id: int = Field(foreign_key="observation.id")
    workflow: str
    provider: str
    model: str
    prompt_version: str
    status: str
    started_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(UTCDateTime(), nullable=False),
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime(), nullable=True),
    )
    latency_ms: Optional[int] = None
    response_raw: Optional[Dict] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    error_reason: Optional[str] = None
    is_mock: bool = True
    prompt_rendered: str
    token_usage: Optional[Dict] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )


# ========== 表7：指标标注（本项目最重要的一张表）==========
class ObservationTag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    observation_id: int = Field(foreign_key="observation.id")
    ai_run_id: Optional[int] = Field(default=None, foreign_key="ai_run.id")

    indicator_code: str    # 如 "1.3"
    indicator_name: str    # 如 "身体行为复杂性"
    level: int             # 1=初阶 / 2=中阶 / 3=高阶

    # ↓↓↓ 这三个字段是"AI 候选采纳率"的唯一数据来源，一个都不能少 ↓↓↓
    source: str                        # ai_suggested / system_determined / teacher_added
    accepted: Optional[bool] = None    # None=还没处理 / True=采纳 / False=否掉
    confidence: Optional[float] = None # AI 的置信度，0~1

    ai_reason: Optional[str] = None          # AI 给的判断理由，让教师快速决定
    rank_in_suggestion: Optional[int] = None # AI 建议时排第几位
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(UTCDateTime(), nullable=False),
    )
    resolved_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(UTCDateTime(), nullable=True),
    )  # 教师处理的时间


# ========== 数据库连接 ==========
engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=True)


def init_db():
    """按上面的定义，在数据库里真的把表建出来"""
    SQLModel.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
    print("✅ 建表完成！")
