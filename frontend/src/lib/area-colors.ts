/**
 * 游戏区域「标识」：每个区域一个低饱和强调色 + 一个代表该区域的小图标。
 *
 * 这不是卡通化的高饱和彩虹配色，而是走暖米纸张 + 低饱和"泥土/植物"色系，
 * 既保留专业绿的整体感，又让教师在一屏里快速区分"哪个区、哪个游戏"。
 * 颜色用淡底、深字保证可读；图标只做辅助标识。
 */
import {
  Blocks,
  BookOpen,
  Drama,
  FlaskConical,
  Mountain,
  Palette,
  Shapes,
  Trees,
  Waves,
  type LucideIcon,
} from "lucide-react";

export interface AreaAccent {
  /** 色点 / 图标强调色 */
  dot: string;
  /** tag 淡色底 */
  chipBg: string;
  /** tag 文字 */
  chipText: string;
  /** 代表该区域的小图标 */
  icon: LucideIcon;
}

const AREA_COLORS: Record<string, AreaAccent> = {
  建构区: { dot: "#b9813f", chipBg: "#f8ecdb", chipText: "#8b5c22", icon: Blocks },
  沙水区: { dot: "#3e8b97", chipBg: "#e3f2f3", chipText: "#2c6b76", icon: Waves },
  攀爬区: { dot: "#c4683a", chipBg: "#f9e8e0", chipText: "#9d4c24", icon: Mountain },
  角色区: { dot: "#a46bb8", chipBg: "#f0e7f6", chipText: "#7b4a90", icon: Drama },
  美工区: { dot: "#c8586e", chipBg: "#f9e5ea", chipText: "#a13a52", icon: Palette },
  阅读区: { dot: "#3e7ca6", chipBg: "#e4eef6", chipText: "#2f6085", icon: BookOpen },
  科探区: { dot: "#2f8f7c", chipBg: "#e2f2ee", chipText: "#1f6f5e", icon: FlaskConical },
  户外综合: { dot: "#6e9c4f", chipBg: "#e9f1e1", chipText: "#53793a", icon: Trees },
};

const NEUTRAL: AreaAccent = {
  dot: "#8b9994",
  chipBg: "#f0efeb",
  chipText: "#5f675f",
  icon: Shapes,
};

/** 按区域中文名取标识；未知区域用中性灰 + 通用图标。 */
export function areaAccent(areaName: string): AreaAccent {
  return AREA_COLORS[areaName] ?? NEUTRAL;
}
