"""MVP 运行配置。"""

import os
from pathlib import Path

# 接入登录后，班级应从当前教师账号取得。
DEFAULT_CLASSROOM_ID = 1

DATABASE_PATH = Path(os.getenv("BANGBANG_DB_PATH", "bangbang.db"))
API_PORT = int(os.getenv("BANGBANG_API_PORT", "8001"))
API_BASE_URL = os.getenv("BANGBANG_API_BASE_URL", f"http://127.0.0.1:{API_PORT}")
UPLOAD_DIR = Path(os.getenv("BANGBANG_UPLOAD_DIR", "uploads"))
