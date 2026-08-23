import { Image as ImageIcon, Plus, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { MediaThumbnail } from "../components/media-thumbnail";
import { MobilePage } from "../components/mobile-page";
import { useTodayMediaData } from "../features/observations/api";
import { OBSERVATION_STATUS_META } from "../features/observations/observation-status";
import {
  compareTimestampsDescending,
  formatLocalTime,
  formatLocalToday,
  isLocalToday,
} from "../lib/date-time";

interface SuccessState { captureDuration?: number }

export function TodayMediaPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const successState = location.state as SuccessState | null;
  const [onlyNeedsReview, setOnlyNeedsReview] = useState(false);
  const { observations, areas, children, media } = useTodayMediaData();

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
  const todayRecords = useMemo(() => (
    (observations.data ?? [])
      .filter((item) => isLocalToday(item.created_at))
      .sort((a, b) => compareTimestampsDescending(a.created_at, b.created_at))
  ), [observations.data]);
  const readyCount = todayRecords.filter((item) => item.status === "ready_for_review").length;
  const visibleRecords = onlyNeedsReview
    ? todayRecords.filter((item) => item.status === "ready_for_review")
    : todayRecords;
  const isLoading = observations.isLoading || areas.isLoading || children.isLoading || media.isLoading;
  const hasError = observations.isError || areas.isError || children.isError || media.isError;

  return (
    <MobilePage>
      <div className="px-5 pb-32 pt-7">
        <header className="mb-6 flex items-end justify-between gap-4">
          <div>
            <p className="mb-1 text-sm font-medium text-ink-muted">{formatLocalToday()}</p>
            <h1 className="text-[30px] font-bold tracking-[-0.03em]">今日素材</h1>
          </div>
          {readyCount > 0 && (
            <button
              aria-pressed={onlyNeedsReview}
              className={`min-h-11 rounded-full px-4 text-sm font-bold ${
                onlyNeedsReview ? "bg-orange-600 text-white" : "bg-orange-100 text-orange-700"
              }`}
              onClick={() => setOnlyNeedsReview((value) => !value)}
              type="button"
            >
              {readyCount} 条待确认
            </button>
          )}
        </header>

        {successState?.captureDuration != null && (
          <button
            className="mb-5 w-full rounded-2xl bg-brand-soft px-4 py-3 text-left text-sm font-medium text-brand-deep"
            onClick={() => navigate(location.pathname, { replace: true, state: null })}
            type="button"
          >
            已存下，稍后整理 · 用时 {Math.round(successState.captureDuration)} 秒
          </button>
        )}

        {isLoading && <p className="py-20 text-center text-sm text-ink-muted">正在看看今天的素材…</p>}
        {hasError && (
          <button
            className="flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-red-200 bg-red-50 text-sm font-medium text-red-700"
            onClick={() => void observations.refetch()}
            type="button"
          >
            <RotateCcw size={16} /> 加载失败，点这里重试
          </button>
        )}

        {!isLoading && !hasError && visibleRecords.length === 0 && (
          <section className="flex min-h-[52vh] flex-col items-center justify-center px-8 text-center">
            <div className="mb-5 grid size-20 place-items-center rounded-[28px] bg-surface text-brand shadow-sm">
              <ImageIcon aria-hidden size={34} strokeWidth={1.7} />
            </div>
            <h2 className="text-lg font-bold">
              {onlyNeedsReview ? "今天没有待确认素材" : "今天还没有素材"}
            </h2>
            <p className="mt-2 text-sm leading-6 text-ink-muted">
              {onlyNeedsReview ? "全部素材都处理好了" : "点下面的按钮开始记录"}
            </p>
          </section>
        )}

        <section className="space-y-3" aria-label="今日素材列表">
          {visibleRecords.map((record) => {
            const status = OBSERVATION_STATUS_META[record.status];
            const itemMedia = mediaByObservation.get(record.id);
            const reviewPath = `/observations/${record.id}/review`;
            const destination = record.status === "confirmed"
              ? `/observations/${record.id}`
              : reviewPath;
            return (
              <Link
                aria-label={`打开${areaNames.get(record.area_id) ?? "未知区域"}记录`}
                className="flex gap-4 rounded-3xl bg-surface p-3 text-inherit shadow-sm"
                key={record.id}
                to={destination}
              >
                <MediaThumbnail
                  className="size-[84px] shrink-0 rounded-2xl"
                  media={itemMedia}
                  mediaType={record.media_type}
                />
                <div className="min-w-0 flex-1 py-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate font-bold">
                      {areaNames.get(record.area_id) ?? "未知区域"} · {formatLocalTime(record.created_at ?? record.observed_at)}
                    </p>
                    <span className={`flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs ${status.className}`}>
                      {record.status === "processing" && (
                        <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-current" />
                      )}
                      {status.label}
                    </span>
                  </div>
                  <p className={`mt-3 text-sm ${record.child_id == null ? "text-stone-400" : "text-ink-muted"}`}>
                    {record.child_id == null ? "未指定幼儿" : childNames.get(record.child_id) ?? "幼儿信息待同步"}
                  </p>
                  {record.status === "failed" && <span className="mt-2 inline-flex min-h-8 items-center text-sm font-bold text-red-700">点开重试</span>}
                </div>
              </Link>
            );
          })}
        </section>
      </div>

      <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200/70 bg-canvas/95 px-5 pt-3">
        <Link className="flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-brand text-lg font-bold text-white shadow-[0_8px_24px_rgba(45,105,80,0.25)]" to="/capture">
          <Plus aria-hidden size={22} /> 记录一下
        </Link>
      </div>
    </MobilePage>
  );
}
