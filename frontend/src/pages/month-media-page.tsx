import { ChevronDown, FolderOpen, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";

import { HomeTabBar } from "../components/home-tab-bar";
import { MaterialCard } from "../components/material-card";
import { MobilePage } from "../components/mobile-page";
import { useTodayMediaData } from "../features/observations/api";
import {
  compareTimestampsDescending,
  getKindergartenYearMonth,
  isKindergartenYearMonth,
} from "../lib/date-time";
import { monthSegments } from "../lib/month-segments";

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

export function MonthMediaPage() {
  const { observations, areas, children, media } = useTodayMediaData();
  const today = getKindergartenYearMonth();
  const [selectedMonth, setSelectedMonth] = useState(today.month);
  const [pickerOpen, setPickerOpen] = useState(false);
  const areaNames = useMemo(() => new Map((areas.data ?? []).map((area) => [area.id, area.name])), [areas.data]);
  const childNames = useMemo(() => new Map((children.data ?? []).map((child) => [child.id, child.name])), [children.data]);
  const mediaByObservation = useMemo(() => new Map((media.data ?? []).filter((item) => item.observation_id != null).map((item) => [item.observation_id as number, item])), [media.data]);
  const monthRecords = useMemo(() => (
    (observations.data ?? [])
      .filter((item) => isKindergartenYearMonth(item.created_at ?? item.observed_at, today.year, selectedMonth))
      .sort((a, b) => compareTimestampsDescending(a.created_at ?? a.observed_at, b.created_at ?? b.observed_at))
  ), [selectedMonth, today.year, observations.data]);
  const groups = useMemo(() => monthSegments(monthRecords, today.year, selectedMonth), [monthRecords, today.year, selectedMonth]);
  const isLoading = observations.isLoading || areas.isLoading || children.isLoading || media.isLoading;
  const hasError = observations.isError || areas.isError || children.isError || media.isError;

  return (
    <MobilePage>
      <div className="min-h-dvh bg-[#f7f6f1] px-4 pb-28 pt-9">
        <header className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-[34px] font-bold tracking-[-0.04em]">月素材</h1>
            <p className="mt-2 text-base text-[#8b9994]">{today.year}年{selectedMonth}月共 {monthRecords.length} 条素材 · 由近及远</p>
          </div>
          <button
            aria-label="选择月份"
            className="mt-1 grid min-h-10 min-w-[5.5rem] shrink-0 grid-cols-[1fr_auto] items-center gap-1 rounded-xl border border-[#dfdcd4] bg-white px-3 font-bold text-brand shadow-sm"
            onClick={() => setPickerOpen(true)}
            type="button"
          >
            <span>{selectedMonth}月</span>
            <ChevronDown size={15} />
          </button>
        </header>

        <div className="mt-6">
          {isLoading && <p className="py-20 text-center text-sm text-ink-muted">正在整理素材…</p>}
          {hasError && <button className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl border border-red-200 bg-red-50 text-sm text-red-700" onClick={() => void observations.refetch()} type="button"><RotateCcw size={16} /> 加载失败，点这里重试</button>}
          {!isLoading && !hasError && monthRecords.length === 0 && (
            <section className="flex min-h-[55vh] flex-col items-center justify-center text-center">
              <div className="grid size-20 place-items-center rounded-[26px] bg-white text-brand shadow-sm"><FolderOpen size={34} /></div>
              <h2 className="mt-5 text-lg font-bold">{selectedMonth}月还没有素材</h2>
            </section>
          )}
          <div className="space-y-7">
            {groups.map((group) => (
              <section key={group.label}>
                <div className="mb-3 flex items-center gap-2">
                  <span className="h-5 w-1 rounded-full bg-brand" />
                  <h2 className="text-base font-medium text-[#8b9994]">{group.label} · {group.records.length} 条</h2>
                </div>
                <div className="space-y-3">
                  {group.records.map((record) => (
                    <MaterialCard areaName={areaNames.get(record.area_id) ?? "未知区域"} childName={record.child_id == null ? "未指定幼儿" : childNames.get(record.child_id) ?? "幼儿信息待同步"} key={record.id} media={mediaByObservation.get(record.id)} record={record} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>

        {pickerOpen && (
          <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/35" role="presentation">
            <button aria-label="关闭月份选择" className="absolute inset-0" onClick={() => setPickerOpen(false)} type="button" />
            <section aria-label="选择月份" className="safe-bottom relative z-10 w-full max-w-[430px] rounded-t-[28px] bg-white px-5 pb-8 pt-6">
              <h2 className="text-xl font-bold">选择月份</h2>
              <div className="mt-4 grid grid-cols-4 gap-3">
                {MONTHS.map((m) => (
                  <button
                    aria-pressed={m === selectedMonth}
                    className={`min-h-11 rounded-xl text-sm font-bold ${m === selectedMonth ? "bg-brand text-white" : "bg-[#f3efe5] text-ink"}`}
                    key={m}
                    onClick={() => { setSelectedMonth(m); setPickerOpen(false); }}
                    type="button"
                  >
                    {m}月
                  </button>
                ))}
              </div>
            </section>
          </div>
        )}
      </div>
      <HomeTabBar active="month" />
    </MobilePage>
  );
}
