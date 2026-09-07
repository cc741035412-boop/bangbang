import { Folder, Inbox, UserRound } from "lucide-react";
import { Link } from "react-router";

const TABS = [
  { key: "today", label: "今日素材", path: "/", icon: Inbox, accent: "#31745a" },
  { key: "month", label: "本月素材", path: "/month", icon: Folder, accent: "#3e7ca6" },
  { key: "mine", label: "我的", path: "/mine", icon: UserRound, accent: "#a46bb8" },
] as const;

export function HomeTabBar({ active }: { active: "today" | "month" | "mine" }) {
  return (
    <nav aria-label="主导航" className="safe-bottom fixed inset-x-0 bottom-0 z-30 mx-auto grid w-full max-w-[430px] grid-cols-3 border-t border-[#dfddd5] bg-white/95 px-2 pt-2 backdrop-blur">
      {TABS.map((tab) => {
        const Icon = tab.icon;
        const selected = tab.key === active;
        return (
          <Link
            aria-current={selected ? "page" : undefined}
            className={`flex min-h-14 flex-col items-center justify-center gap-1 text-xs ${selected ? "font-bold" : "font-medium text-[#99a29e]"}`}
            key={tab.key}
            style={{ color: selected ? tab.accent : undefined }}
            to={tab.path}
          >
            <Icon aria-hidden fill={selected ? "currentColor" : "none"} size={24} strokeWidth={1.8} />
            <span>{tab.label}</span>
            {selected && <span aria-hidden className="mt-0.5 h-1 w-7 rounded-full" style={{ backgroundColor: tab.accent }} />}
          </Link>
        );
      })}
    </nav>
  );
}
