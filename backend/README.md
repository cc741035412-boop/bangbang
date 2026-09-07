# 后端

## 文件职责

| 文件 | 作用 |
|---|---|
| `main.py` | API 入口与路由 |
| `models.py` | SQLModel 数据表 |
| `indicators.py` | 观察指标字典与区域先验 |
| `person_service.py` | 白描人物引用归组、线索提取与教师姓名对应校验 |
| `ai_service.py` | 白描、候选指标及分析策略；支持模拟模式和外部模型 |
| `run_demo.py` | 在新临时目录启动本机模拟体验，不使用现有业务库 |
| `seed.py` | 虚构基础测试数据 |
| `migrate.py` | 可重复运行的 SQLite 迁移 |
| `demo.py` | 端到端演示脚本 |
| `requirements.txt` | Python 依赖 |

## 运行约定

- 所有后端命令都从 `backend/` 目录执行。
- 本地虚拟环境固定为 `backend/.venv/`。
- 默认业务路径为 `backend/bangbang.db` 与 `backend/uploads/`，禁止自动化写入已有业务数据。
- 体验运行使用 `python run_demo.py`，数据库和上传目录由启动器隔离到新临时目录；所有 AI 与短信固定为模拟模式。
- 数据库、上传素材、缓存和虚拟环境不进入版本控制。
- 新增测试时放入 `backend/tests/`，文件命名为 `test_<feature>.py`。
