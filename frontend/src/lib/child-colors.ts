/**
 * 幼儿头像/档案的区分色。
 *
 * 给每个幼儿一个稳定、柔和的身份色（按 id 取模），让"幼儿档案库 / 记录里的
 * 幼儿标签"更鲜活、更易区分。颜色走低饱和、暖调，不与专业冲突，也不卡通化。
 */

const CHILD_COLORS = [
  { bg: "#e7f0e4", text: "#3f6b4a", dot: "#5c8a63" }, // 绿
  { bg: "#e8eef7", text: "#3a5f8a", dot: "#4f7bb0" }, // 蓝
  { bg: "#f7ece2", text: "#8a5a2f", dot: "#b9813f" }, // 暖橙
  { bg: "#f3e8f2", text: "#7b4a78", dot: "#a46bb8" }, // 紫
  { bg: "#f8e8e9", text: "#9c3f47", dot: "#c8586e" }, // 玫红
  { bg: "#e3f1f0", text: "#2c6b6b", dot: "#3e8b8a" }, // 青
  { bg: "#f0efe2", text: "#6c6a3f", dot: "#8a8a4f" }, // 橄榄
  { bg: "#eef0f7", text: "#474f8a", dot: "#5a64a8" }, // 靛蓝
] as const;

export function childAccent(id: number) {
  return CHILD_COLORS[Math.abs(id) % CHILD_COLORS.length] ?? CHILD_COLORS[0];
}
