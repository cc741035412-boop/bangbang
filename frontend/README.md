# 前端开发规则

## 1. 技术栈

| 层级 | 选择 | 版本策略 | 用途 |
|---|---|---|---|
| 运行环境 | Node.js | 22 LTS | 本地开发和构建 |
| 包管理 | npm | 随 Node 22 | 只维护 `package-lock.json` |
| UI 框架 | React | 19.x | 组件与交互 |
| 语言 | TypeScript | 5.x，strict | 类型安全 |
| 构建工具 | Vite | 8.x | SPA 开发、构建和代理 |
| 路由 | React Router | 7.x，声明式模式 | 四个 MVP 页面导航 |
| 服务端状态 | TanStack Query | 5.x | 请求、缓存、加载和错误状态 |
| API 类型 | openapi-typescript + openapi-fetch | 7.x / 当前稳定版 | 从 FastAPI OpenAPI 生成类型安全客户端 |
| 样式 | Tailwind CSS | 4.x | 移动端布局与设计令牌 |
| 图标 | Lucide React | 当前稳定版 | 统一线性图标 |
| 单元/组件测试 | Vitest + Testing Library | 4.x / 当前稳定版 | 业务逻辑与交互测试 |
| 端到端测试 | Playwright | 当前稳定版 | MVP 主流程测试，首个页面闭环完成后接入 |

安装时锁定实际版本到 `package-lock.json`，不要手写猜测精确补丁版本。升级主版本前先记录影响并验证完整主流程。

## 2. 为什么采用这套方案

- 当前产品是调用独立 FastAPI 的手机端工具，不需要服务端渲染，因此选择 Vite SPA，不采用 Next.js。
- React 的资料、组件生态和 AI 辅助编码覆盖更广，适合快速完成培训项目并持续迭代。
- TypeScript 和 OpenAPI 类型生成减少前后端字段不一致。
- TanStack Query只管理远端数据；页面临时状态仍使用 React 本地状态。
- Tailwind CSS 便于快速实现移动端界面，但设计令牌必须集中定义，禁止随意堆叠无规则颜色和尺寸。

## 3. 明确不采用

MVP 阶段不引入：

- Next.js、React Router Framework Mode 或服务端渲染
- Redux、Zustand 等全局状态库
- Axios
- shadcn/ui、Ant Design、Material UI 等组件系统
- React Hook Form 和 Zod；表单复杂度证明有需要时再加入
- PWA、离线队列、Service Worker 和原生应用封装
- 国际化、主题切换和园长端响应式桌面布局

需要新增依赖时，先说明它解决的具体问题；浏览器原生能力或现有依赖能解决时不新增。

## 4. 目录结构

```text
frontend/
├── public/                 # 不经过构建处理的静态文件
├── src/
│   ├── api/                # API 客户端、请求封装、OpenAPI 生成类型
│   │   └── generated/      # 自动生成，禁止手工修改
│   ├── app/                # 应用入口、路由、QueryClient 和全局 Provider
│   ├── assets/             # 源码引用的图片、字体等
│   ├── components/         # 跨页面复用的基础组件
│   ├── features/           # 按业务能力组织
│   │   ├── media/          # 素材选择、上传和状态
│   │   └── observations/   # 白描、指标确认、分析与记录
│   ├── pages/              # 路由级页面
│   ├── styles/             # Tailwind 入口、设计令牌和少量全局样式
│   ├── test/               # 测试初始化和共享测试工具
│   └── main.tsx            # 浏览器入口
├── index.html
├── package.json
├── package-lock.json
├── tsconfig.json
└── vite.config.ts
```

组织原则：

1. 页面只负责组装，不直接写底层请求。
2. 业务请求和 Query hooks 放在对应 `features/` 中。
3. 只有被两个以上页面复用的组件才进入 `components/`。
4. 禁止建立含义不明的 `utils/` 大杂烩；工具函数靠近所属功能。
5. OpenAPI 生成文件统一放入 `src/api/generated/`，不得手工修改。

## 5. 路由约定

首版只设四个业务页面：

| 路径 | 页面 |
|---|---|
| `/` | 今日素材 |
| `/capture` | 快速沉淀 |
| `/observations/:observationId/review` | AI 整理与教师确认 |
| `/observations/:observationId` | 观察记录详情 |

使用 React Router 声明式模式。数据请求由 TanStack Query 处理，不使用 Router loader/action 重复建立第二套数据层。

## 6. 状态管理边界

- 后端数据：TanStack Query。
- 上传进度与处理状态：TanStack Query mutation/query，加页面局部状态。
- 表单输入、选择和弹层：React `useState` 或 `useReducer`。
- 跨页面必要标识：URL 路径或查询参数。
- 不把后端响应复制进全局状态。
- 不使用 Context 保存频繁变化的业务数据；Context 只用于稳定的应用级依赖。

## 7. API 约定

- 开发环境统一通过 Vite `/api` 代理到 `http://127.0.0.1:8000`，避免为本地开发修改后端 CORS。
- 前端代码只调用 `/api`，不得散落硬编码的后端域名。
- 使用 `openapi-typescript` 从后端 `/openapi.json` 生成类型。
- 使用 `openapi-fetch` 作为轻量类型安全客户端，不使用 Axios。
- 请求失败必须转为用户可理解的错误状态，禁止只打印 `console.error`。
- mock AI 响应的 `is_mock` 和 `notice` 必须在界面可见。

环境变量：

- 仅使用 `VITE_` 前缀。
- 前端环境变量都是公开配置，禁止放密钥、token 或密码。
- 本地默认通过代理访问，不依赖 `.env` 才能启动。

## 8. 样式与移动端约定

- Mobile First，首要验证宽度为 375px 和 390px。
- 页面内容最大宽度保持手机阅读体验，桌面端居中展示，不扩展成管理后台。
- 触摸目标最小 44×44px。
- 正文最小字号 14px，主要输入与按钮不小于 16px。
- 颜色、圆角、间距、阴影通过 Tailwind 4 的 CSS 主题变量统一定义。
- “系统判定”“AI 建议”“教师确认”必须使用不同但一致的视觉语义，不能只靠颜色区分。
- 优先使用原生语义元素和可访问标签；图标按钮必须有文字或 `aria-label`。
- 不使用 emoji 充当产品图标。

## 9. 计划中的命令

脚手架建立后，`package.json` 至少提供：

```bash
npm run dev          # 启动开发服务器
npm run typecheck    # tsc --noEmit
npm run lint         # ESLint
npm run test         # Vitest 单次运行
npm run build        # 类型检查后构建
npm run api:generate # 从 FastAPI OpenAPI 生成类型
```

增加 Playwright 后再提供 `npm run test:e2e`。

## 10. 完成标准

每个前端功能完成前必须：

1. 在 375px 和 390px 宽度下检查主要交互。
2. 覆盖加载、空数据、成功、失败和可恢复状态。
3. 运行 `npm run typecheck`、`npm run lint`、`npm run test` 和 `npm run build`。
4. 与真实 FastAPI 接口完成至少一次联调。
5. AI 候选保留教师采纳、否决和补充入口。
6. 未经教师确认的记录不显示为正式记录。
