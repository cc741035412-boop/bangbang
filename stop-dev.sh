#!/usr/bin/env bash
# 停止「帮帮师记」前后端。
for port in 8001 5173; do
  pid=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  if [ -n "$pid" ]; then kill "$pid" 2>/dev/null && echo "已停止 端口 $port (进程 $pid)"; else echo "端口 $port 未在运行"; fi
done
