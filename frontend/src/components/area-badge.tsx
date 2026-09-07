import { areaAccent } from "../lib/area-colors";

/** 展示游戏区域：小图标 + 区域名，按该区域专属色着色（弱化单调、强化区界）。 */
export function AreaBadge({ name, className = "" }: { name: string; className?: string }) {
  const accent = areaAccent(name);
  const Icon = accent.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${className}`}
      style={{ backgroundColor: accent.chipBg, color: accent.chipText }}
    >
      <Icon aria-hidden size={13} strokeWidth={2} />
      {name}
    </span>
  );
}
