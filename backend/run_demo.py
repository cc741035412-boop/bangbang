"""本机模拟体验启动器：每次使用新临时目录，不读取已有业务数据库。"""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    data = Path(tempfile.mkdtemp(prefix="bangbang-demo-"))
    (data / "README.md").write_text(
        "本机模拟体验数据。demo.db 为临时库，uploads/ 为模拟素材。"
        "每次启动创建新目录，不自动清理，不可提交到 Git。\n", encoding="utf-8"
    )
    (data / "uploads").mkdir()
    env = os.environ.copy()
    env.update(
        BANGBANG_DB_PATH=str(data / "demo.db"),
        BANGBANG_UPLOAD_DIR=str(data / "uploads"),
        BANGBANG_ENV="development",
        BANGBANG_ALLOWED_HOSTS="localhost,127.0.0.1,testserver",
        BANGBANG_AI_MODE="mock",
        BANGBANG_VISION_MODE="mock",
        BANGBANG_ASR_MODE="mock",
        BANGBANG_SQL_ECHO="false",
        SMS_PROVIDER="mock",
        SMS_MOCK_CODE="123456",
    )
    backend = Path(__file__).resolve().parent
    subprocess.run([sys.executable, "bootstrap.py"], cwd=backend, env=env, check=True)
    print("模拟体验已使用独立临时数据；不会调用外部 AI 或发送短信。", flush=True)
    print("数据目录：" + str(data), flush=True)
    print("请在前端注册虚构账号；模拟验证码见体验页面。Ctrl+C 停止服务。", flush=True)
    os.chdir(backend)
    os.execve(sys.executable, [sys.executable, "-m", "uvicorn", "main:app",
                            "--host", "127.0.0.1", "--port", str(args.port),
                            "--no-access-log"], env)


if __name__ == "__main__":
    main()
