import { ChevronRight, Download, FolderOpen, LogOut, PersonStanding, School, Search, Settings, ShieldCheck } from "lucide-react";
import { useMemo, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { HomeTabBar } from "../components/home-tab-bar";
import { MobilePage } from "../components/mobile-page";
import { PwaInstallCard } from "../components/pwa-install-card";
import { FEATURES } from "../config/features";
import { useLogout } from "../features/auth/api";
import { useAuth } from "../features/auth/auth-context-value";
import { getMonthlyExportUrl, useTodayMediaData } from "../features/observations/api";
import { useSettingsData } from "../features/settings/api";
import { childAccent } from "../lib/child-colors";
import { getKindergartenYearMonth, isKindergartenYearMonth } from "../lib/date-time";

export function MinePage() {
  const navigate = useNavigate();
  const { observations } = useTodayMediaData();
  const { children, teachers } = useSettingsData();
  const { account } = useAuth();
  const logout = useLogout();
  const currentMonth = getKindergartenYearMonth();
  const teacher = teachers.data?.[0];
  const displayName = account?.name ?? teacher?.name;
  const confirmed = useMemo(
    () => (observations.data ?? []).filter((record) => record.status === "confirmed"),
    [observations.data],
  );
  const childCounts = useMemo(() => {
    const counts = new Map<number, number>();
    confirmed.forEach((record) => {
      if (record.child_id != null) counts.set(record.child_id, (counts.get(record.child_id) ?? 0) + 1);
    });
    return counts;
  }, [confirmed]);
  const monthCount = confirmed.filter((record) =>
    isKindergartenYearMonth(record.created_at ?? record.observed_at, currentMonth.year, currentMonth.month),
  ).length;
  const isLoading = observations.isLoading || children.isLoading || teachers.isLoading;
  const hasError = observations.isError || children.isError || teachers.isError;

  // 还没接后端的能力一律不出现入口，避免出现点不动的按钮
  const notConnected = ([
    !FEATURES.auth && "账号",
    !FEATURES.kindergarten && "园所",
    !FEATURES.childMutation && "幼儿新增与删除",
    !FEATURES.exportHistory && "导出历史",
  ] as (string | false)[]).filter((item): item is string => typeof item === "string");

  return (
    <MobilePage>
      <div className="min-h-dvh bg-[#f7f6f1] px-4 pb-28 pt-10">
        <h1 className="sr-only">我的</h1>
        <header className="flex items-center gap-4">
          <div className="grid size-16 shrink-0 place-items-center rounded-full bg-[#e7f3ed] text-2xl font-bold text-brand">
            {displayName?.trim().charAt(0) || "师"}
          </div>
          <div>
            <h2 className="text-2xl font-bold">
              {displayName || (teachers.isLoading ? "正在加载…" : "未填写教师")}
            </h2>
            <p className="mt-1 text-sm text-[#8b9994]">
              {account?.kindergarten_name
                ? `${account.kindergarten_name}${account.classroom_name ? ` · ${account.classroom_name}` : ""}`
                : "当前教师"}
            </p>
          </div>
        </header>

        {hasError && (
          <p className="mt-5 rounded-xl bg-red-50 px-3 py-3 text-sm text-red-700">
            部分信息加载失败，请刷新页面重试
          </p>
        )}

        <SectionTitle hint={`${children.data?.length ?? 0} 名`} icon={<PersonStanding className="text-brand" size={19} />}>幼儿档案库</SectionTitle>
        <section
          aria-label="幼儿档案库"
          className="overflow-x-auto rounded-2xl border border-[#dfdcd4] bg-white px-4 py-5"
        >
          {isLoading ? (
            <p className="text-sm text-ink-muted">正在加载幼儿信息…</p>
          ) : (
            <div className="flex min-w-max gap-7">
              {(children.data ?? []).map((child) => {
                const avatar = childAccent(child.id);
                const inner = (
                  <>
                    <div
                      className="mx-auto grid size-14 place-items-center rounded-full text-xl font-bold"
                      style={{ backgroundColor: avatar.bg, color: avatar.text }}
                    >
                      {child.name.trim().charAt(0) || "幼"}
                    </div>
                    <p className="mt-2 truncate font-medium">{child.name}</p>
                    <p className="mt-1 text-xs text-[#8b9994]">{childCounts.get(child.id) ?? 0} 条</p>
                  </>
                );
                // 档案详情没接后端时，头像不做成可点的，避免点进去是空页
                return FEATURES.childProfile ? (
                  <Link className="w-16 text-center text-inherit" key={child.id} to={`/children/${child.id}`}>
                    {inner}
                  </Link>
                ) : (
                  <div className="w-16 text-center" key={child.id}>
                    {inner}
                  </div>
                );
              })}
              {(children.data ?? []).length === 0 && (
                <p className="text-sm text-ink-muted">暂无幼儿信息</p>
              )}
            </div>
          )}
        </section>

        <SectionTitle>我的记录</SectionTitle>
        <section className="space-y-3">
          <RowLink icon={<Search className="text-brand" size={22} />} label="检索观察记录" to="/records" />

          <a
            className="flex min-h-16 items-center gap-3 rounded-2xl border border-[#dfdcd4] bg-white px-4 text-inherit"
            download
            href={getMonthlyExportUrl(currentMonth.year, currentMonth.month, true)}
          >
            <Download className="text-[#b9813f]" size={22} />
            <span className="flex-1 font-medium">导出本月 Word</span>
            <span className="text-sm text-[#8b9994]">{monthCount} 篇</span>
            <ChevronRight className="text-[#c5cbc8]" size={19} />
          </a>

          {FEATURES.exportHistory && (
            <RowLink icon={<FolderOpen className="text-[#3e7ca6]" size={22} />} label="导出记录" to="/exports" />
          )}

          <RowLink icon={<Settings className="text-[#8b9994]" size={22} />} label="基础信息设置" to="/settings" />

          {FEATURES.childMutation && (
            <RowLink icon={<PersonStanding className="text-[#2f8f7c]" size={22} />} label="管理幼儿档案" to="/children" />
          )}
        </section>

        {(FEATURES.auth || FEATURES.kindergarten) && (
          <>
            <SectionTitle>账号</SectionTitle>
            <section className="space-y-3">
              {FEATURES.auth && (
                <RowLink
                  icon={<ShieldCheck className="text-brand" size={22} />}
                  label="账号与安全"
                  to="/account"
                  value={account ? maskPhone(account.phone) : undefined}
                />
              )}
              {FEATURES.kindergarten && (
                <RowLink
                  icon={<School className="text-[#a46bb8]" size={22} />}
                  label="所在园所"
                  to="/kindergarten"
                  value={account?.kindergarten_name ?? undefined}
                />
              )}
              {FEATURES.auth && account && (
                <button
                  className="flex min-h-16 w-full items-center gap-3 rounded-2xl border border-[#dfdcd4] bg-white px-4 text-left"
                  disabled={logout.isPending}
                  onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login", { replace: true }) })}
                  type="button"
                >
                  <LogOut className="text-[#c8853a]" size={22} />
                  <span className="flex-1 font-medium text-[#c8853a]">退出登录</span>
                  <ChevronRight className="text-[#c5cbc8]" size={19} />
                </button>
              )}
            </section>
          </>
        )}

        {notConnected.length > 0 && (
          <p className="mt-7 rounded-2xl bg-[#efeee9] px-4 py-3 text-sm leading-6 text-ink-muted">
            {notConnected.join("、")}尚未接入后端，因此本页不展示这些入口。
          </p>
        )}

        <SectionTitle>体验版</SectionTitle>
        <PwaInstallCard />
      </div>
      <HomeTabBar active="mine" />
    </MobilePage>
  );
}

function RowLink({
  icon,
  label,
  to,
  value,
}: {
  icon: ReactNode;
  label: string;
  to: string;
  value?: string;
}) {
  return (
    <Link
      className="flex min-h-16 items-center gap-3 rounded-2xl border border-[#dfdcd4] bg-white px-4 text-inherit"
      to={to}
    >
      {icon}
      <span className="flex-1 font-medium">{label}</span>
      {value && <span className="text-sm text-[#8b9994]">{value}</span>}
      <ChevronRight className="text-[#c5cbc8]" size={19} />
    </Link>
  );
}

function SectionTitle({ children, hint, icon }: { children: ReactNode; hint?: string; icon?: ReactNode }) {
  return (
    <div className="mb-3 mt-8 flex items-center gap-2">
      <span className="h-6 w-1 rounded bg-brand" />
      {icon && <span className="grid size-6 place-items-center rounded-full bg-white">{icon}</span>}
      <h2 className="text-xl font-bold">{children}</h2>
      {hint && <span className="ml-auto text-sm text-[#8b9994]">{hint}</span>}
    </div>
  );
}

function maskPhone(phone: string) {
  return phone.length === 11 ? `${phone.slice(0, 3)}****${phone.slice(7)}` : phone;
}
