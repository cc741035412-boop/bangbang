# 后端

## 文件职责

| 文件 | 作用 |
|---|---|
| `main.py` | API 入口与路由 |
| `models.py` | SQLModel 数据表 |
| `indicators.py` | 观察指标字典与区域先验 |
| `ai_service.py` | AI 服务边界，当前为 mock |
| `seed.py` | 虚构基础测试数据 |
| `migrate.py` | 可重复运行的 SQLite 迁移 |
| `demo.py` | 端到端演示脚本 |
| `requirements.txt` | Python 依赖 |

## 运行约定

- 所有后端命令都从 `backend/` 目录执行。
- 本地虚拟环境固定为 `backend/.venv/`。
- SQLite 数据库固定为 `backend/bangbang.db`。
- 上传素材固定为 `backend/uploads/`，仅允许模拟素材。
- 数据库、上传素材、缓存和虚拟环境不进入版本控制。
- 新增测试时放入 `backend/tests/`，文件命名为 `test_<feature>.py`。
