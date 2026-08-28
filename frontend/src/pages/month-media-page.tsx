import { FolderOpen, RotateCcw } from "lucide-react";
import { useMemo } from "react";

import { HomeTabBar } from "../components/home-tab-bar";
import { MaterialCard } from "../components/material-card";
import { MobilePage } from "../components/mobile-page";
import { useTodayMediaData, type Observation } from "../features/observations/api";
import {
  compareTimestampsDescending,
  formatKindergartenDate,
  getKindergartenDateKey,
  getKindergartenYearMonth,
  isKindergartenToday,
  isKindergartenYearMonth,
} from "../lib/date-time";

export function MonthMediaPage() {
  const { observations, areas, children, media } = useTodayMediaData();
  const currentMonth = getKindergartenYearMonth();
  const areaNames = useMemo(() => new Map((areas.data ?? []).map((area) => [area.id, area.name])), [areas.data]);
  const childNames = useMemo(() => new Map((children.data ?? []).map((child) => [child.id, child.name])), [children.data]);
  const mediaByObservation = useMemo(() => new Map((media.data ?? []).filter((item) => item.observation_id != null).map((item) => [item.observation_id as number, item])), [media.data]);
  const monthRecords = useMemo(() => (
    (observations.data ?? [])
      .filter((item) => isKindergartenYearMonth(item.created_at ?? item.observed_at, currentMonth.year, currentMonth.month))
      .sort((a, b) => compareTimestampsDescending(a.created_at ?? a.observed_at, b.created_at ?? b.observed_at))
  ), [currentMonth.month, currentMonth.year, observations.data]);
  const groups = useMemo(() => groupByDate(monthRecords), [monthRecords]);
  const isLoading = observations.isLoading || areas.isLoading || children.isLoading || media.isLoading;
  const hasError = observations.isError || areas.isError || children.isError || media.isError;

  return (
    <MobilePage>
      <div className="min-h-dvh bg-[#f7f6f1] px-4 pb-28 pt-9">
        <header><h1 className="text-[34px] font-bold tracking-[-0.04em]">本月素材</h1><p className="mt-2 text-base text-[#8b9994]">{currentMonth.month}月共 {monthRecords.length} 条素材 · 最新的在最上面</p></header>
        <div className="mt-6">
          {isLoading && <p className="py-20 text-center text-sm text-ink-muted">正在整理本月素材…</p>}
          {hasError && <button className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl border border-red-200 bg-red-50 text-sm text-red-700" onClick={() => void observations.refetch()} type="button"><RotateCcw size={16} /> 加载失败，点这里重试</button>}
          {!isLoading && !hasError && monthRecords.length === 0 && <section className="flex min-h-[55vh] flex-col items-center justify-center text-center"><div className="grid size-20 place-items-center rounded-[26px] bg-white text-brand shadow-sm"><FolderOpen size={34} /></div><h2 className="mt-5 text-lg font-bold">这个月还没有素材</h2></section>}
          <div className="space-y-6">
            {groups.map(({ dateKey, records }) => (
              <section key={dateKey}>
                <h2 className="mb-3 text-base font-medium text-[#8b9994]">{formatKindergartenDate(records[0].created_at ?? records[0].observed_at)}{isKindergartenToday(records[0].created_at ?? records[0].observed_at) ? " · 今天" : ""}</h2>
                <div className="space-y-3">{records.map((record) => <MaterialCard areaName={areaNames.get(record.area_id) ?? "未知区域"} childName={record.child_id == null ? "未指定幼儿" : childNames.get(record.child_id) ?? "幼儿信息待同步"} key={record.id} media={mediaByObservation.get(record.id)} record={record} />)}</div>
              </section>
            ))}
          </div>
        </div>
      </div>
      <HomeTabBar active="month" />
    </MobilePage>
  );
}

function groupByDate(records: Observation[]) {
  const groups = new Map<string, Observation[]>();
  records.forEach((record) => {
    const key = getKindergartenDateKey(record.created_at ?? record.observed_at);
    groups.set(key, [...(groups.get(key) ?? []), record]);
  });
  return [...groups].map(([dateKey, values]) => ({ dateKey, records: values }));
}
