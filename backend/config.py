"""MVP 运行配置。"""

import os
from pathlib import Path

from dotenv import load_dotenv


ENV_FILE = Path(__file__).with_name(".env")
load_dotenv(ENV_FILE)

# 接入登录后，班级应从当前教师账号取得。
DEFAULT_CLASSROOM_ID = 1
# 接入登录后，当前教师应从账号会话取得。
DEFAULT_TEACHER_ID = 1
DEFAULT_TEACHER_NAME = "默认教师"

DATABASE_PATH = Path(os.getenv("BANGBANG_DB_PATH", "bangbang.db"))
API_PORT = int(os.getenv("BANGBANG_API_PORT", "8001"))
API_BASE_URL = os.getenv("BANGBANG_API_BASE_URL", f"http://127.0.0.1:{API_PORT}")
UPLOAD_DIR = Path(os.getenv("BANGBANG_UPLOAD_DIR", "uploads"))
SQL_ECHO = os.getenv("BANGBANG_SQL_ECHO", "false").strip().lower() == "true"

RUNTIME_ENV = os.getenv("BANGBANG_ENV", "development").strip().lower()
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "").strip().lower()
SMS_MOCK_CODE = os.getenv("SMS_MOCK_CODE", "123456").strip()

AI_MODE = os.getenv("BANGBANG_AI_MODE", "mock").strip().lower()
if AI_MODE not in {"mock", "deepseek"}:
    raise ValueError("BANGBANG_AI_MODE 只能是 mock 或 deepseek")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# ---- 工作流 A（客观白描）多模态视觉配置 ----
# 默认 mock；接入豆包视觉时在 .env 里设为 doubao。
VISION_MODE = os.getenv("BANGBANG_VISION_MODE", "mock").strip().lower()
if VISION_MODE not in {"mock", "doubao"}:
    raise ValueError("BANGBANG_VISION_MODE 只能是 mock 或 doubao")

# 火山方舟（豆包）视觉模型。
ARK_API_KEY = os.getenv("BANGBANG_ARK_API_KEY", "")
DOUBAO_VISION_MODEL = os.getenv(
    "BANGBANG_DOUBAO_VISION_MODEL", "doubao-seed-1-6-vision-250815"
)
DOUBAO_VISION_API_URL = os.getenv(
    "BANGBANG_DOUBAO_VISION_API_URL",
    "https://ark.cn-beijing.volces.com/api/v3/responses",
)

# ---- 工作流 A 配套：音频转写（ASR，复用火山方舟豆包多模态 & 同一把 ark Key）----
# 默认 mock（demo 阶段不真转写）；接入后在 .env 设为 doubao。
ASR_MODE = os.getenv("BANGBANG_ASR_MODE", "mock").strip().lower()
if ASR_MODE == "volc":  # 兼容旧命名（语音控制台），实际也走方舟豆包
    ASR_MODE = "doubao"
if ASR_MODE not in {"mock", "doubao"}:
    raise ValueError("BANGBANG_ASR_MODE 只能是 mock 或 doubao")

ASR_API_KEY = ARK_API_KEY  # 复用方舟 ark Key
ASR_MODEL = os.getenv("BANGBANG_ASR_MODEL", DOUBAO_VISION_MODEL)  # 默认复用视觉接入点（已验证支持音频）
ASR_API_URL = os.getenv(
    "BANGBANG_ASR_API_URL",
    "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
)
ASR_TIMEOUT_SECONDS = int(os.getenv("BANGBANG_ASR_TIMEOUT_SECONDS", "120"))
