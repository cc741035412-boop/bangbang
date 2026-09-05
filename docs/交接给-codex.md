# 帮帮师记 · 项目交接说明（给 codex）

你接手的是一个**已经在跑的真实项目**，不是从零开始。
先把这份文档读完再动手。所有接口细节在同目录的 `未接入功能-接口契约.md`。

---

## 一、这个产品是什么，为什么这么做

**帮帮师记**：把幼儿园老师随手拍的照片和视频，变成一篇能交给园所存档、能发给家长看的观察记录。

产品负责人 dawei 是幼教教研员出身、现在转做 AI 产品，**不写代码**。
所以：**任何需要他决策的地方，用大白话说清楚代价，不要用技术术语让他盲签。**

这个产品的立项依据来自三组真实调研，写进代码注释里的很多"为什么"都指向它们：

- **F 组（访谈发现）**：老师每月要写 12 篇观察记录；三位受访老师全部在凌晨 1 点写；
  100% 自费买工具；卡点是"素材不结构化"+"连不上理论"；素材不当场沉淀，全靠回忆重建。
- **G 组（竞品缺口）**：市面四家产品的指标打标全是人工，AI 与结构之间那一步是空白。
- **E 组（AI 实测证据）**：
  - **E1** 照片版 AI 会整段幻觉 → 以视频为主输入，选照片时界面必须提示
  - **E2** 视频版能抓到教师原话，与教师自己的 PPT 一字不差 → **必须保留音频**
  - **E3** AI 与专家的三个差距：只会夸、太通用、没有连续性

**MVP 范围**：只做观察记录一个出口。指标覆盖**首期只做两个维度**——
「身体参与」全部要点（层级分界是时长，视频可直接算，零幻觉）、
「社会互动」中肉眼可见的行为（轮流、分工、和谁玩、说了什么）。
**不做**「社会情感」的品质推断（共情能力、专注品质）——那是伦理问题，不是准确率问题。

---

## 二、不可动摇的规则（改这些之前必须先问 dawei）

这几条不是代码风格，是产品能不能拿到有效数据的前提。

1. **指标勾选框一律默认不勾。** 预选会污染采纳率数据——我们要靠采纳率判断 AI 到底行不行。
2. **把握程度只显示三档**（把握不大 / 有一些把握 / 较有把握），**不显示原始置信度数值**。
3. **「我不确定」区块不可折叠、不可隐藏。** 「AI 这次没给出有用建议」本身就是要采集的数据。
4. **教师改写白描时保留 AI 原始版本**（`narrativeAI`，不展示），用来算白描可用率。
5. **只有教师勾选采纳的指标才进完整稿正文。** 未勾选的不出现。
6. **幼儿档案的维度统计只是"被观察到几次"。**
   后端**不得返回任何评级、评分、百分位、同班对比**。
   一旦返回可比较的数值，这个工具就会从"老师的镜子"变成"给孩子打分的表"。
7. **不做假按钮、不做假数据入口。** 没接后端的功能，入口就不出现，
   而不是做一个点了没反应或者假装成功的按钮。
8. **删除类操作不提供级联删除参数。** 删班级、删幼儿时若名下还有数据，
   返回 409 + 一句中文说明，让人先去处理。级联删除是误删数据最常见的来源，
   而这些数据是老师熬夜攒出来的。
9. **错误响应统一 `{ "detail": "老师能看懂的中文" }`**，前端会原样显示给老师。
10. **幼儿影像上传外部服务器的合规性尚未闭环。**
    在 dawei 明确说闭环之前，AI 相关能力保持 mock，不要接任何公网大模型。

三个必须保留的埋点：`trackAdopt`（指标采纳率）、`trackNarrativeEdit`（白描可用率）、`trackUseless`。

---

## 三、代码现状

仓库根目录 `~/bangbang`：`backend/` `frontend/` `docs/` `uploads/` `outputs/`

**前端**：React 19 + Vite 8 + TypeScript + TanStack Query v5 + react-router v7 +
Tailwind v4（`@theme` 定义色板）+ lucide-react + openapi-fetch。

色板 token：`brand #31745a` / `brand-deep #225440` / `brand-soft #dcebe3` /
`canvas #efeee9` / `surface #fffefa` / `ink #242520` / `ink-muted #676960`。
手机壳 `MobilePage` 固定 `max-w-[430px]`。

**已经跑通的主链路**（后端已实现）：
上传素材 → AI 白描 → 候选指标逐条采纳（含"我自己加一条"）→ 确认 → 完整稿 → Word 导出 → 系统分享。

**已写完但等后端的前端**（2026-08-27 加）：
登录/注册/账号与安全、园所与班级、PDF/Markdown 导出、导出历史、
幼儿档案详情、新增删除幼儿、多幼儿关联上传。

---

## 四、能力开关机制（这是本项目最重要的约定）

`frontend/src/config/features.ts`：

```ts
export const FEATURES = {
  auth: false,              // 登录 / 退出 / 账号与安全
  kindergarten: false,      // 园所与班级
  exportDocx: true,         // 已通
  exportPdf: false,
  exportMarkdown: false,
  exportHistory: false,
  childProfile: false,      // 幼儿档案详情
  childMutation: false,     // 新增 / 删除幼儿
  multiChildCapture: false, // 一条素材关联多个幼儿
};
```

**后端做好一项，把对应的 `false` 改成 `true`，界面自动放开。不要改 UI 代码。**

为 `false` 时的降级行为已经写好了：
独立页面自己 `Navigate` 跳回 `/mine`，「我的」页不渲染入口；
导出格式置灰标「暂未开放」，不可选中也不发请求；
`RequireAuth` 整体放行，现有流程完全不受影响。

新接口暂时走 `frontend/src/api/http.ts`（手写 fetch 封装），
因为 `src/api/generated/schema.d.ts` 由后端 `openapi.json` 生成，
后端没有的路径写进 `apiClient` 会直接 typecheck 失败。
**全部接口上线后跑 `npm run api:generate`，把调用换成 `apiClient`，再删掉 `http.ts`。**

---

## 五、怎么干活

**一次只做一节。** 做完一项、验一项、翻一个开关，再做下一项。
不要一口气把七项都做了——出问题时无法定位是哪一项坏的。

**顺序**（按 `未接入功能-接口契约.md` 的编号）：

| 序 | 功能 | 开关 | 状态 |
|---|---|---|---|
| 1 | 登录 / 退出 / 账号与安全 | `auth` | ✅ 已完成（2026-08-28） |
| 3 | PDF / Markdown 导出 | `exportPdf` `exportMarkdown` | ✅ 已完成，docx/pdf/md 三种格式均已实测 |
| 5 | 幼儿档案详情 | `childProfile` | ✅ 已完成 |
| 6 | 新增 / 删除幼儿 | `childMutation` | ✅ 已完成 |
| 4 | 导出历史 | `exportHistory` | ✅ 已完成（`export_records` 表已建，见 `migration-20260828-kindergarten-export.md`） |
| 7 | 多幼儿关联上传 | `multiChildCapture` | ✅ 已完成 |
| 2 | 园所与班级 | `kindergarten` | ✅ 已完成（`classroom.kindergarten_id` 已迁移回填） |

> 2026-08-28 更新：上述功能后端接口与前端页面均已就绪，开关全部为 `true`。
> 前端 `/api` 代理默认端口已由 8000 修正为 8001（与后端默认一致）。
> 下一步：多模态接入，方案见 `multimodal-integration-plan.md`，等 dawei 拍板后实施。

**每做完一项**：
```
cd frontend && npm run typecheck && npm run lint && npm test
```
然后按契约文档第 8 节的验收清单手点一遍。

**涉及数据库 schema 变更时必须先问 dawei**，这是项目铁律，不要自作主张。
问的时候要说清楚：新增哪几张表、现有表动不动、真实 `bangbang.db` 要不要迁移。

**对真实 `bangbang.db` 执行迁移前，必须先备份**：
```
cp bangbang.db bangbang.db.bak-$(date +%Y%m%d)
```
备份失败就停下来，不要继续。

---

## 六、第 1 节（登录）当前进度

已经改了 7 个文件、+848 −10，包括：
`backend/.env.example`、`backend/config.py`、`backend/main.py`、
`backend/migrate_auth.py`、`backend/models.py`、`backend/tests/test_auth.py`、
`frontend/src/config/features.ts`。

新增四张表：`kindergartens`、`accounts`、`sms_codes`、`auth_sessions`。
现有 `teacher` / `classroom` 表不动，账号表关联园所和教师。

dawei 已批准的三件事：
1. 批准新增这四张表及迁移代码（`auth_sessions` 是必要的，没有它退出登录是假的）
2. 接受本地阶段固定验证码 `123456`，但必须：
   - 由环境变量控制（如 `SMS_PROVIDER=mock`），**不要写成 `if DEBUG` 之类的硬编码分支**
   - 生产环境未配置真实短信供应商时，发送接口直接报错，**不允许回落到固定验证码**
   - **验证码不得打进日志**
   - 60 秒限流、5 分钟过期、一次性消费这三条对 mock 同样生效
3. 授权本轮对真实 `bangbang.db` 执行迁移，但顺序必须是：
   临时库跑通全部测试 → 备份 `bangbang.db` → 迁移真实库 → **最后**才把 `auth` 改成 `true`

`sms_codes.purpose` 至少要区分 `login` / `register` / `change_phone` / `delete_account`，
否则登录用的验证码可以拿来注销账号。

注册时**同名园所不自动并入已有园所**——同名幼儿园很多，误并会让两个园互相看到对方的幼儿数据。
新建独立园所，注册者 `role = owner`。

---

## 七、下一步

先把第 1 节收尾：确认上述三条约束都落实了，测试通过，迁移按顺序做完，
`auth` 翻成 `true` 后手点一遍完整登录流程（注册 → 刷新仍在登录态 → 退出 → 被挡回 `/login` → 重新登录）。

然后进第 3 节（PDF / Markdown 导出）。

有任何需要 dawei 拍板的地方，用大白话问，说清楚两个选项各自的代价。
