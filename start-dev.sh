#!/usr/bin/env bash
# 启动「帮帮师记」前后端（后台常驻：关掉终端 / 退出会话也不会停）。
# 用法：./start-dev.sh    停止：./stop-dev.sh
ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG="$ROOT/work/devlogs"
mkdir -p "$LOG"

echo ">> 已在运行的旧进程将自动停掉"
for port in 8001 5173; do
  pid=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  if [ -n "$pid" ]; then kill "$pid" 2>/dev/null && echo "  已停掉 端口 $port (旧进程 $pid)"; fi
done
sleep 1

echo ">> 启动后端 (8001)"
cd "$ROOT/backend"
SMS_PROVIDER=mock SMS_MOCK_CODE=123456 BANGBANG_ENV=development nohup .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001 --log-level warning > "$LOG/backend.log" 2>&1 &
echo "  后端日志 -> $LOG/backend.log"

echo ">> 启动前端 (5173)"
cd "$ROOT/frontend"
nohup npm run dev -- --port 5173 --strictPort > "$LOG/frontend.log" 2>&1 &
echo "  前端日志 -> $LOG/frontend.log"

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "你的局域网IP")
echo ""
echo "稍等 5~8 秒后访问："
echo "  电脑  http://localhost:5173"
echo "  手机  http://$LAN_IP:5173   （同一 WiFi）"
echo "启动失败就看上面的日志文件排查。"
