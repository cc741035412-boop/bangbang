import { RotateCcw, SearchX } from "lucide-react";
import { useMemo, useState } from "react";

import { MaterialCard } from "../components/material-card";
import { MobilePage } from "../components/mobile-page";
import {
  useAllMedia,
  useAreas,
  useChildren,
  useIndicators,
  useObservationSearch,
  type Observation,
  type ObservationSearchFilters,
} from "../features/observations/api";
import {
  compareTimestampsDescending,
  formatKindergartenDate,
  getKindergartenDateKey,
  getKindergartenTodayKey,
  isKindergartenToday,
  kindergartenMonthStartKey,
} from "../lib/date-time";
import { PageHeader } from "./account-page";

// 状态只保留教师真正关心、能一眼看懂的四档，不暴露底层 processing/failed。
const STATUS_OPTIONS: { value: Observation["status"] | ""; label: string }[] = [
  { value: "", label: "全部状态" },
  { value: "ready_for_review", label: "草稿状态" },
  { value: "uploaded", label: "待生成状态" },
  { value: "confirmed", label: "已生成状态" },
];

type DateMode = "all" | "today" | "month" | "custom";

const DATE_MODES: { value: DateMode; label: string }[] = [
  { value: "all", label: "全部时间" },
  { value: "today", label: "本日" },
  { value: "month", label: "本月" },
  { value: "custom", label: "自定义日期" },
];

export function RecordSearchPage() {
  const [childId, setChildId] = useState("");
  const [areaId, setAreaId] = useState("");
  const [status, setStatus] = useState<Observation["status"] | "">("");
  const [indicatorCode, setIndicatorCode] = useState("");
  const [dateMode, setDateMode] = useState<DateMode>("all");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");

  const todayKey = getKindergartenTodayKey();

  // 把日期模式换算成实际查询的起止（北京时间自然日）。自定义下只填一个也当作单日。
  const dateRange = useMemo(() => {
    if (dateMode === "today") return { from: todayKey, to: todayKey };
    if (dateMode === "month") {
      return { from: kindergartenMonthStartKey(todayKey), to: todayKey };
    }
    if (dateMode === "custom") {
      const from = customFrom || customTo || "";
      const to = customTo || customFrom || "";
      const invalid = customFrom !== "" && customTo !== "" && customFrom > customTo;
      return invalid ? { from: "", to: "" } : { from, to };
    }
    return { from: "", to: "" };
  }, [customFrom, customTo, dateMode, todayKey]);
  const rangeInvalid = (
    dateMode === "custom" && customFrom !== "" && customTo !== "" && customFrom > customTo
  );

  const filters = useMemo<ObservationSearchFilters>(() => ({
    child_id: childId === "" ? undefined : Number(childId),
    area_id: areaId === "" ? undefined : Number(areaId),
    status: status === "" ? undefined : status,
    indicator_code: indicatorCode || undefined,
    date_from: dateRange.from || undefined,
    date_to: dateRange.to || undefined,
  }), [childId, areaId, status, indicatorCode, dateRange.from, dateRange.to]);

  const observations = useObservationSearch(filters);
  const areas = useAreas();
  const children = useChildren();
  const indicators = useIndicators();
  const media = useAllMedia();

  const areaNames = useMemo(
    () => new Map((areas.data ?? []).map((area) => [area.id, area.name])),
    [areas.data],
  );
  const childNames = useMemo(
    () => new Map((children.data ?? []).map((child) => [child.id, child.name])),
    [children.data],
  );
  const mediaByObservation = useMemo(
    () => new Map(
      (media.data ?? [])
        .filter((item) => item.observation_id != null)
        .map((item) => [item.observation_id as number, item]),
    ),
    [media.data],
  );

  const records = useMemo(() => observations.data ?? [], [observations.data]);
  const sorted = useMemo(
    () => [...records].sort((a, b) => (
      compareTimestampsDescending(a.observed_at, b.observed_at)
    )),
    [records],
  );
  const groups = useMemo(() => groupByDate(sorted), [sorted]);

  const isLoading = (
    observations.isLoading || areas.isLoading || children.isLoading
    || indicators.isLoading || media.isLoading
  );
  const hasError = observations.isError || areas.isError || children.isError
    || indicators.isError || media.isError;

  const isFiltering = childId !== "" || areaId !== "" || status !== ""
    || indicatorCode !== "" || dateMode !== "all";

  function resetFilters() {
    setChildId("");
    setAreaId("");
    setStatus("");
    setIndicatorCode("");
    setDateMode("all");
    setCustomFrom("");
    setCustomTo("");
  }

  return (
    <MobilePage>
      <main className="min-h-dvh bg-[#f7f6f1] px-4 pb-20 pt-5">
        <PageHeader subtitle="按幼儿、区域和观察日期翻找旧记录" title="检索记录" />

        <section className="mt-6 rounded-2xl border border-[#dfdcd4] bg-white p-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="幼儿">
              <Select
                aria-label="幼儿"
                onChange={setChildId}
                options={[
                  { value: "", label: "全部幼儿" },
                  ...(children.data ?? []).map((child) => ({
                    value: String(child.id),
                    label: child.name,
                  })),
                ]}
                value={childId}
              />
            </Field>
            <Field label="游戏区域">
              <Select
                aria-label="游戏区域"
                onChange={setAreaId}
                options={[
                  { value: "", label: "全部区域" },
                  ...(areas.data ?? []).map((area) => ({
                    value: String(area.id),
                    label: area.name,
                  })),
                ]}
                value={areaId}
              />
            </Field>
          </div>

          <div className="mt-3">
            <Field label="状态">
              <Select
                aria-label="状态"
                onChange={(value) => setStatus(value as Observation["status"] | "")}
                options={STATUS_OPTIONS}
                value={status}
              />
            </Field>
          </div>

          <div className="mt-3">
            <Field label="观察指标">
              <Select
                aria-label="观察指标"
                onChange={setIndicatorCode}
                options={[
                  { value: "", label: "全部指标" },
                  ...(indicators.data ?? []).map((indicator) => ({
                    value: indicator.indicator_code,
                    label: `${indicator.indicator_code} ${indicator.indicator_name} · ${indicator.level_label}`,
                  })),
                ]}
                value={indicatorCode}
              />
            </Field>
          </div>

          <div className="mt-3">
            <span className="mb-1 block text-xs text-[#8b9994]">观察日期（北京时间）</span>
            <div className="flex flex-wrap items-center gap-2">
              {DATE_MODES.map((mode) => (
                <Chip
                  active={dateMode === mode.value}
                  key={mode.value}
                  label={mode.label}
                  onClick={() => setDateMode(mode.value)}
                />
              ))}
              {isFiltering && <Chip label="重置筛选" onClick={resetFilters} />}
            </div>

            {dateMode === "custom" && (
              <div className="mt-3 grid grid-cols-2 gap-3">
                <input
                  aria-label="起始日期"
                  className="h-11 w-full rounded-xl border border-[#dfdcd4] bg-[#f7f6f1] px-3 text-[15px] text-ink outline-none focus:border-brand"
                  max={customTo || undefined}
                  onChange={(event) => setCustomFrom(event.target.value)}
                  type="date"
                  value={customFrom}
                />
                <input
                  aria-label="截止日期"
                  className="h-11 w-full rounded-xl border border-[#dfdcd4] bg-[#f7f6f1] px-3 text-[15px] text-ink outline-none focus:border-brand"
                  min={customFrom || undefined}
                  onChange={(event) => setCustomTo(event.target.value)}
                  type="date"
                  value={customTo}
                />
              </div>
            )}

            {dateMode === "today" && (
              <p className="mt-2 text-xs text-ink-muted">只看 {todayKey} 当天的记录</p>
            )}
            {dateMode === "month" && (
              <p className="mt-2 text-xs text-ink-muted">
                本月 {kindergartenMonthStartKey(todayKey)} ~ {todayKey}
              </p>
            )}
            {dateMode === "custom" && (customFrom !== "" || customTo !== "") && !rangeInvalid && (
              <p className="mt-2 text-xs text-ink-muted">
                {customTo && customFrom && customFrom !== customTo
                  ? `${customFrom} ~ ${customTo}`
                  : `只看 ${customFrom || customTo} 当天的记录`}
              </p>
            )}
            {rangeInvalid && (
              <p className="mt-2 text-xs text-red-600">开始日期不能晚于结束日期，已暂不按日期过滤</p>
            )}
          </div>
        </section>

        <p className="mb-3 mt-6 text-sm text-[#8b9994]">
          已加载 {records.length} 条记录 · 最新的在最上面
        </p>

        {isLoading && <p className="py-20 text-center text-sm text-ink-muted">正在检索记录…</p>}
        {hasError && (
          <button
            className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl border border-red-200 bg-red-50 text-sm text-red-700"
            onClick={() => {
              void observations.refetch();
              void areas.refetch();
              void children.refetch();
              void indicators.refetch();
              void media.refetch();
            }}
            type="button"
          >
            <RotateCcw size={16} /> 加载失败，点这里重试
          </button>
        )}
        {!isLoading && !hasError && records.length === 0 && (
          <section className="flex min-h-[45vh] flex-col items-center justify-center text-center">
            <div className="grid size-20 place-items-center rounded-[26px] bg-white text-brand shadow-sm">
              <SearchX size={34} />
            </div>
            <h2 className="mt-5 text-lg font-bold">没有找到符合条件的记录</h2>
            <p className="mt-2 text-sm text-ink-muted">换个幼儿、区域或时间范围再试试</p>
          </section>
        )}

        <div className="space-y-6">
          {groups.map(({ dateKey, records: dayRecords }) => dayRecords[0] && (
            <section key={dateKey}>
              <h2 className="mb-3 text-base font-medium text-[#8b9994]">
                {formatKindergartenDate(dayRecords[0].observed_at)}
                {isKindergartenToday(dayRecords[0].observed_at) ? " · 今天" : ""}
              </h2>
              <div className="space-y-3">
                {dayRecords.map((record) => (
                  <MaterialCard
                    areaName={areaNames.get(record.area_id) ?? "未知区域"}
                    childName={
                      record.child_id == null
                        ? "未指定幼儿"
                        : childNames.get(record.child_id) ?? "幼儿信息待同步"
                    }
                    key={record.id}
                    media={mediaByObservation.get(record.id)}
                    record={record}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>

        {!hasError && observations.hasNextPage && (
          <button
            className="mt-6 min-h-12 w-full rounded-2xl border border-brand/25 bg-white font-bold text-brand disabled:text-ink-muted"
            disabled={observations.isFetchingNextPage}
            onClick={() => void observations.fetchNextPage()}
            type="button"
          >
            {observations.isFetchingNextPage ? "正在加载…" : "加载更多记录"}
          </button>
        )}
      </main>
    </MobilePage>
  );
}

function groupByDate(records: Observation[]) {
  const groups = new Map<string, Observation[]>();
  records.forEach((record) => {
    const key = getKindergartenDateKey(record.observed_at);
    groups.set(key, [...(groups.get(key) ?? []), record]);
  });
  return [...groups].map(([dateKey, values]) => ({ dateKey, records: values }));
}

function Field({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-[#8b9994]">{label}</span>
      {children}
    </label>
  );
}

function Select({ value, onChange, options, ...rest }: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  "aria-label"?: string;
}) {
  return (
    <select
      {...rest}
      className="h-11 w-full rounded-xl border border-[#dfdcd4] bg-[#f7f6f1] px-3 text-[15px] text-ink outline-none focus:border-brand"
      onChange={(event) => onChange(event.target.value)}
      value={value}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  );
}

function Chip({ active, label, onClick }: { active?: boolean; label: string; onClick: () => void }) {
  return (
    <button
      className={
        active
          ? "rounded-full bg-brand px-3 py-1 text-xs text-white"
          : "rounded-full border border-[#dfdcd4] bg-[#f7f6f1] px-3 py-1 text-xs text-ink-muted active:bg-brand-soft active:text-brand-deep"
      }
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}
