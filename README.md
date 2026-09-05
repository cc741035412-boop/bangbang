# 帮帮师记

面向幼儿园主班教师的结构化观察素材工具。已跑通 FastAPI 后端 + 手机端 Web/PWA 前端。

## 目录

```text
.
├── CLAUDE.md          # 全项目规则
├── backend/           # FastAPI 服务
├── frontend/          # 手机端 Web/PWA
├── docs/              # 产品、流程、接口与测试文档
├── work/              # 临时过程文件
└── outputs/           # 最终交付物
```

## 快速启动（一键，后台常驻，推荐）

在项目根目录执行：

```bash
./start-dev.sh     # 启动前端 + 后端（后台常驻：关掉终端也不会停）
./stop-dev.sh      # 停止前后端
```

启动后打开：

- 网页/手机端：<http://localhost:5173>（手机上用同一 WiFi，具体地址看脚本每次启动打印的 `http://<你的局域网IP>:5173`）
- 后端接口文档：<http://127.0.0.1:8001/docs>
- 健康检查：<http://127.0.0.1:8001/health>

- 日志：`work/devlogs/backend.log`、`work/devlogs/frontend.log`
- 登录：任意 11 位手机号 + 验证码 `123456`（mock）

> 为什么关掉终端服务还能保持运行？脚本用 `nohup` 后台启动，进程不依赖终端会话。
> 之前在前台 `uvicorn` / `npm run dev`，一关终端就收到 `SIGHUP` 被杀掉，服务就停了。

> 服务与编辑器无关：关掉 VS Code / Cursor **不影响**前端运行（后台常驻）。
> 请用普通终端跑 `./start-dev.sh`，不要在编辑器内启动服务。
> 已在其用户配置中关闭终端响铃与音频提示音（`terminal.integrated.enableBell`、`accessibility.signals.*`）。

## 手动启动后端（不推荐，仅调试用）

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python seed.py
SMS_PROVIDER=mock SMS_MOCK_CODE=123456 BANGBANG_ENV=development uvicorn main:app --host 0.0.0.0 --port 8001
```

`bangbang.db`、`.venv/`、`uploads/` 和 `work/devlogs/` 都是本地运行时数据，不属于源码。
