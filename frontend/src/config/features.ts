/**
 * 后端能力开关。
 *
 * 规则（沿用产品既定原则）：没有后端的功能不做假按钮、不做假数据入口。
 * 这里为 false 的能力，界面要么不出现入口，要么明确显示为"尚未接入"，
 * 不允许出现点了没反应或者假装成功的情况。
 *
 * codex：后端做好一个，把对应的 false 改成 true，界面自动放开，不用改 UI 代码。
 */
export const FEATURES = {
  /** 手机号验证码登录 / 退出登录 / 账号与安全 */
  auth: true,
  /** 园所与班级管理 */
  kindergarten: true,
  /** 导出格式：docx / pdf 已通（Markdown 已停用，改为带图片的报告/表格形式） */
  exportDocx: true,
  exportPdf: true,
  exportMarkdown: false,
  /** 导出历史（需要后端建表记录每次导出） */
  exportHistory: true,
  /** 幼儿档案详情页（聚合统计 + 该幼儿的记录列表） */
  childProfile: true,
  /** 新增 / 删除幼儿 */
  childMutation: true,
  /** 一条素材关联多个幼儿 */
  multiChildCapture: true,
} as const;

export type FeatureKey = keyof typeof FEATURES;

export function isEnabled(key: FeatureKey) {
  return FEATURES[key];
}
