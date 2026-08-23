# 帮帮师记

面向幼儿园主班教师的结构化观察素材工具。当前仓库包含已跑通的 FastAPI 后端，手机端前端尚未开始。

## 目录

```text
.
├── CLAUDE.md          # 全项目规则
├── backend/           # FastAPI 服务
├── frontend/          # 手机端 Web/PWA（待建立）
├── docs/              # 产品、流程、接口与测试文档
├── work/              # 临时过程文件
└── outputs/           # 最终交付物
```

## 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python seed.py
uvicorn main:app --reload
```

打开：

- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

另开一个终端运行完整演示：

```bash
cd backend
source .venv/bin/activate
python demo.py
```

`bangbang.db`、`.venv/` 和 `uploads/` 都是本地运行时数据，不属于源码。
