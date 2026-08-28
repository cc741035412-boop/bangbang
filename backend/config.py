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
