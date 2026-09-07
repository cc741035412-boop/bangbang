"""生产部署前只读检查；失败时以非零状态退出，不修改数据库或文件。"""

import os
from pathlib import Path

from config import (
    AI_MODE,
    ALLOWED_HOSTS,
    ARK_API_KEY,
    ASR_MODE,
    DATABASE_PATH,
    DEEPSEEK_API_KEY,
    RUNTIME_ENV,
    SMS_PROVIDER,
    UPLOAD_DIR,
    VISION_MODE,
)


def production_errors():
    errors = []
    if RUNTIME_ENV not in {"demo", "production", "prod"}:
        errors.append("BANGBANG_ENV 必须设为 demo 或 production")
    if RUNTIME_ENV in {"production", "prod"} and SMS_PROVIDER in {"", "mock"}:
        errors.append("生产环境必须接入真实短信服务，不能使用 mock 验证码")
    if RUNTIME_ENV == "demo" and SMS_PROVIDER != "mock":
        errors.append("公开模拟体验环境必须显式使用 SMS_PROVIDER=mock")
    if (
        not ALLOWED_HOSTS
        or "*" in ALLOWED_HOSTS
        or set(ALLOWED_HOSTS) <= {"localhost", "127.0.0.1", "testserver"}
    ):
        errors.append("BANGBANG_ALLOWED_HOSTS 必须明确列出公网域名，不能使用通配符")
    if not DATABASE_PATH.is_absolute():
        errors.append("BANGBANG_DB_PATH 必须是持久磁盘上的绝对路径")
    if not UPLOAD_DIR.is_absolute():
        errors.append("BANGBANG_UPLOAD_DIR 必须是持久磁盘上的绝对路径")
    if DATABASE_PATH.resolve() == Path("bangbang.db").resolve():
        errors.append("生产环境不能使用仓库内默认数据库路径")
    if UPLOAD_DIR.resolve() == Path("uploads").resolve():
        errors.append("生产环境不能使用仓库内默认上传目录")
    if AI_MODE == "deepseek" and not DEEPSEEK_API_KEY:
        errors.append("BANGBANG_AI_MODE=deepseek 时必须配置 DEEPSEEK_API_KEY")
    if (VISION_MODE == "doubao" or ASR_MODE == "doubao") and not ARK_API_KEY:
        errors.append("启用豆包视觉或语音时必须配置 BANGBANG_ARK_API_KEY")
    return errors


if __name__ == "__main__":
    problems = production_errors()
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}")
        raise SystemExit(1)
    print(f"{RUNTIME_ENV} 环境配置检查通过")
