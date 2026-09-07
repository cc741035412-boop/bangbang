# 帮帮师记 —— 公开体验版部署与上线验收清单

> 状态：部署前可执行准备稿（含红线步骤说明）
> 更新日期：2026-09-05
> 用途：把「可安装 PWA + 公开演示网址 + 源码」这一形态的上线落到可复现的清单。
> 与 `docs/launch-test-plan.md` 的关系：那份方案负责「测什么数据、测到什么程度」；本清单负责「怎么把环境布起来、上线前逐项验收什么」。

## 1. 目标与范围

- 交付形态：**可安装 PWA**（manifest + 图标 + 独立窗口 + 基础离线壳）+ 公开演示网址 + GitHub 源码。
- 暂不做：App Store / Android APK / iOS 原生安装（涉及 Apple 开发者签名、证书与审核；Capacitor 等原生封装在 PWA 稳定后再评估）。
- 环境性质：**模拟体验环境**，只承载虚构幼儿、模拟素材与演示账号，不承载园所真实业务数据。

## 2. 前置构建 / 测试校验（发布前必须全绿）

在 `frontend/` 下执行，全部通过才算可发布：

| 项 | 命令 | 预期 |
|---|---|---|
| 前端测试 | `npm test` | 全部通过（当前 69 个） |
| 生产构建 + 产物校验 | `npm run build:check`（先 `typecheck`+`vite build`，再跑 `scripts/validate-build.mjs`） | 构建成功，且产物校验通过（manifest/图标/sw/HTML 引用完整） |
| 前端 Lint | `npm run lint` | 无错误 |
| 后端测试 | `python -m pytest tests/ -q`（在 `backend/`，需 `.venv`） | 全部通过（当前 84 个） |

后端生产配置只读校验（在 `backend/`，指向持久磁盘与公网域名时）应通过，否则会以非零退出：

```bash
BANGBANG_ENV=production \
SMS_PROVIDER=<真实短信供应商> \
BANGBANG_DB_PATH=/absolute/persistent/bangbang.db \
BANGBANG_UPLOAD_DIR=/absolute/persistent/uploads \
BANGBANG_ALLOWED_HOSTS=your-domain.example \
python production_check.py
```

> 注意：`production_check.py` 会拒绝 `SMS_PROVIDER=mock`。若未接入真实短信，只能发布**明确标注的模拟体验环境**，并将验证码锁定为 mock 且给出用户可见提示。

## 3. 部署运行步骤（红线：执行前需逐项获得确认）

### 3.1 免费朋友体验（Render）

1. 将最终代码推送到公开 GitHub 仓库。
2. 在 Render 使用仓库根目录的 `render.yaml` 创建 Blueprint；选择免费计划，不绑定付费磁盘或自有域名。
3. Render 使用 `deploy/Dockerfile.render` 将 React PWA 与 FastAPI 构建为同一个 HTTPS 服务，健康检查路径为 `/api/health`。
4. 免费实例文件系统不持久化：休眠、重启或重新部署后，SQLite、上传素材和体验账号都会重置。这是公开虚构数据演示的限制，也是默认清理机制。
5. 取得 `*.onrender.com` 地址后完成第 5 节验收，并把真实体验链接与截图补回 README。

### 3.2 自有服务器部署

1. **持久磁盘**：为 SQLite 与上传目录准备持久化卷（单实例约束）。`compose.public.yaml` 已把 `BANGBANG_DB_PATH`/`BANGBANG_UPLOAD_DIR` 指向 `/data/*` 并挂载独立的 `bangbang-public-data` 卷。
2. **环境变量**：公开模拟体验设置 `PUBLIC_HOST`、独立六位 `SMS_MOCK_CODE` 与 `BANGBANG_ENV=demo`；正式业务环境必须改为 `production` 并接入真实短信服务。实际值只保存在服务器，不写入仓库。
3. **空库初始化**：服务启动命令已内建 `python bootstrap.py`（建表 + 写入 8 个区域字典，不含个人信息）。空环境首次启动即完成初始化。
4. **构建镜像**：`docker compose -f compose.public.yaml up -d --build`。Caddy 使用 `PUBLIC_HOST` 自动申请 HTTPS 证书；香港或海外临时演示可使用 `bangbang-<公网IP>.nip.io`。
5. **只读生产检查**：执行第 2 节的 `production_check.py` 确认配置无红项。
6. **对外可访问性**：Caddy 负责 80/443 与 HTTPS，frontend nginx 在 `/api/` 反代到 backend；两层入口均启用必要安全响应头，上传上限为 200MB。

## 4. 安全与数据边界（对外必须遵守）

- 只能使用**虚构幼儿、模拟素材、演示账号**；禁止真实幼儿姓名/影像/教师隐私/园所内部材料进入公开环境。
- **AI 输出不等于教师专业结论**：客观白描由 AI 主笔、教师核对；观察指标由教师最终采纳/否定；分析与措施由教师主笔。注册页应能从用户协议/隐私说明处访问到「仅供模拟体验」提示。
- **保存期限与清理**：体验数据需明确保存期限并定期清理；清理执行仍遵守「用户逐条授权」规则。清理策略：对指定日期范围的历史演示数据，在独立临时库上先做只读核对，再按 `created_at` 或账号维度清理，任何删除在 `bangbang.db` 上需授权。
- 对外 README 不提供真实验证码、密钥、内部域名配置或真实数据恢复方式。

## 5. 上线前验收清单（逐项打勾）

| # | 验收项 | 方法 |
|---|---|---|
| 1 | 后端 `/health` 返回成功、`/docs` 可打开 | 请求公网域名的 `/health`、`/docs` |
| 2 | 核心端到端流程可跑通 | 用虚构账号走一遍「上传素材 → AI 整理 → 教师确认 → 保存」 |
| 3 | 权限隔离 | 尝试用 A 账号的 `observation_id` / `media_id` 访问 B 账号数据，应 404/401；幼儿、班级、导出、AI 接口均需登录态 |
| 4 | 上传限制 | 超过 200MB 被拒；视频超过 3 分钟被拒；不支持格式被拒 |
| 5 | 敏感文件检查 | 确认容器内不暴露 `bangbang.db`、`uploads/`、`.env`、密钥、日志、导出文件（`.dockerignore` 已排除） |
| 6 | PWA 可安装 | 手机/桌面能添加到主屏幕；`manifest` 可解析；安装后独立窗口打开；图标正常 |
| 7 | 375px / 390px 页面 | 在浏览器模拟 375×812 与 390×844（iPhone 尺寸）逐页目测无横向滚动、关键按钮可用、底部安全区不遮挡 |
| 8 | mock 提示 | 所有 mock 输出带 `is_mock: true` 与用户可见提示 |

## 6. 截图拍摄清单（面向对外 README）

在浏览器/真机上按以下画面截图，放入 `outputs/` 或 README 引用（避免纳入源码目录）：

1. 登录页（含「仅供模拟体验」提示）
2. 今日素材页（含「上传素材」入口）
3. 快速存素材底页（文件 + 游戏区域两步）
4. 现场：AI 白描 + 候选指标确认页
5. 观察记录检索页（筛选 + 分页）
6. 已确认记录详情 / 导出
7. 手机「添加到主屏幕」安装示意（375/390 之一）
8. 已安装后在桌面打开 app 的效果

## 7. 红线步骤（需用户逐项确认后执行）

- 公开发布（部署到公网、绑定域名/密钥）——CLAUDE.md 第 9.7 条：部署配置、CI/CD、域名、密钥和公开发布均需单独确认。
- `git commit` 与 `git push`（发布提交）——CLAUDE.md 第 10 条：提交前检查暂存区与工作区、只提交最终确认版本、不提交数据库/素材/密钥/日志/中间产物。

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-04 | 初稿：把公开体验版的目标、前置校验、部署步骤、安全边界、验收与截图清单落到文档 |
| 2026-09-05 | 同步当前自动化测试基线，并补充 README 的本地运行、功能、隐私与公网部署说明 |
