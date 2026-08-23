# 前端技术决策

> 状态：已决定  
> 日期：2026-08-22  
> 适用范围：帮帮师记 MVP 手机端

## 1. 决策

采用 React 19、TypeScript 5、Vite 8 构建纯客户端单页应用，配合 React Router 7 声明式路由、TanStack Query 5、OpenAPI TypeScript、openapi-fetch 和 Tailwind CSS 4。

测试使用 Vitest 4 与 Testing Library；完成首个端到端闭环后加入 Playwright。

## 2. 决策依据

### 产品阶段

当前任务是验证四个手机页面组成的 MVP，不需要 SEO、服务端渲染、复杂权限或多端共享渲染。纯客户端 SPA 是最短路径。

### 与现有后端匹配

后端已通过 FastAPI 暴露 OpenAPI 3.1 文档。使用 `openapi-typescript` 生成类型，再由 `openapi-fetch` 发起请求，可以把接口路径、参数、请求体和响应类型直接纳入 TypeScript 检查，减少手写类型与后端漂移。

### 数据特点

页面数据主要来自后端：素材列表、观察记录、候选指标和处理状态。TanStack Query适合处理请求缓存、加载、错误、重试和刷新。它只承担服务端状态，避免引入 Redux 一类通用全局状态方案。

### 学习与维护成本

React、Vite 和 TypeScript 有成熟的官方文档与生态。项目只采用 React Router 的声明式模式，不同时引入 Router loaders/actions 与 TanStack Query，避免两套数据流。

## 3. 为什么不选其他方案

### 不选 Next.js

MVP 没有 SEO、服务端渲染或全栈 React 的必要。Next.js 会引入服务器组件、渲染边界和额外部署决策，与当前独立 FastAPI 后端重复。

### 不选 Vue

Vue同样能完成任务，但 React 在 AI 辅助编码示例、组件生态和后续职业迁移上更通用。本项目没有现成 Vue 代码或团队经验需要继承，因此选择 React。

### 不选 React Router Framework Mode

Framework Mode提供服务端渲染、路由模块和数据加载能力，但当前已有 TanStack Query 和 FastAPI。首版使用声明式模式足够表达四个页面。

### 不选 Redux 或 Zustand

当前没有复杂跨页面客户端状态。后端数据交给 TanStack Query，临时表单状态留在组件内，URL承担可分享的导航状态。

### 不选重型组件库

Ant Design 和 Material UI更偏通用后台或既定视觉体系；MVP 是教师手机端，核心页面数量少。直接建立少量语义化组件更容易控制触摸尺寸、信息层级和三种权责状态。

### 首版不做 PWA

安装、离线缓存和后台上传尚未被验证为必要需求。先验证手机浏览器中的主流程；只有教师明确受到网络或入口问题阻碍时，再引入 PWA 与离线队列。

## 4. 版本与环境

- 当前本机：Node.js 22.23.2、npm 10.9.8。
- Vite 8要求 Node.js 20.19+ 或 22.12+，当前环境满足要求。
- 项目使用 Node 22，不依赖全局安装的前端 CLI。
- 依赖的精确补丁版本由初始化时生成的 `package-lock.json` 锁定。

## 5. 架构边界

```text
React pages
    ↓
feature components + TanStack Query hooks
    ↓
typed API client (openapi-fetch)
    ↓
generated OpenAPI types
    ↓
FastAPI /openapi.json
```

- 页面不直接拼接 URL 或调用裸 `fetch`。
- 自动生成类型不能手工修改。
- 开发环境由 Vite 把 `/api` 代理到 FastAPI。
- 生产部署策略不在本次决策范围内。

## 6. 重新评估触发条件

出现以下事实之一时，重新评估而不是提前建设：

- 教师必须从系统分享菜单快速进入，普通网页入口显著影响留存。
- 弱网环境导致素材经常丢失，需要可恢复上传或离线队列。
- 产品需要推送通知、后台上传或更深的相机能力。
- 需要公开内容被搜索引擎收录或服务端渲染。
- 出现大量复杂表单，原生 React 状态明显难以维护。
- 多页面共享的客户端状态无法由 URL 或服务端数据表达。

## 7. 下一步

已完成：按上述规则初始化前端基础工程并建立四个空路由。

下一步：第一条功能切片——“今日素材 → 快速沉淀 → 上传素材”。

## 8. 参考资料

- [Vite 8 发布说明](https://vite.dev/blog/announcing-vite8)
- [Vite 入门与 Node.js 要求](https://vite.dev/guide/)
- [React 19](https://react.dev/blog/2024/12/05/react-19)
- [React Router 模式选择](https://reactrouter.com/start/modes)
- [TanStack Query 概览](https://tanstack.com/query/latest/docs/framework/react/overview)
- [OpenAPI TypeScript](https://openapi-ts.dev/introduction)
- [openapi-fetch](https://openapi-ts.dev/openapi-fetch/)
- [Tailwind CSS 4](https://tailwindcss.com/blog/tailwindcss-v4)
- [Vitest 4](https://vitest.dev/blog/vitest-4)
