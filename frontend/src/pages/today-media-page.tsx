import { Blocks, Image as ImageIcon, RotateCcw } from "lucide-react";
import { useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { HomeTabBar } from "../components/home-tab-bar";
import { MaterialCard } from "../components/material-card";
import { MobilePage } from "../components/mobile-page";
import { UploadSheet } from "../components/upload-sheet";
import { useTodayMediaData } from "../features/observations/api";
import { compareTimestampsDescending, formatKindergartenToday, isKindergartenToday } from "../lib/date-time";

export function TodayMediaPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { observations, areas, children, media } = useTodayMediaData();
  const areaNames = useMemo(() => new Map((areas.data ?? []).map((area) => [area.id, area.name])), [areas.data]);
  const childNames = useMemo(() => new Map((children.data ?? []).map((child) => [child.id, child.name])), [children.data]);
  const mediaByObservation = useMemo(() => new Map((media.data ?? []).filter((item) => item.observation_id != null).map((item) => [item.observation_id as number, item])), [media.data]);
  const todayRecords = useMemo(() => (
    (observations.data ?? [])
      .filter((item) => isKindergartenToday(item.created_at ?? item.observed_at))
      .sort((a, b) => compareTimestampsDescending(a.created_at ?? a.observed_at, b.created_at ?? b.observed_at))
  ), [observations.data]);
  const isLoading = observations.isLoading || areas.isLoading || children.isLoading || media.isLoading;
  const hasError = observations.isError || areas.isError || children.isError || media.isError;
  const uploadOpen = searchParams.get("upload") === "1";

  function closeUpload() {
    setSearchParams({}, { replace: true });
  }

  return (
    <MobilePage>
      <div className="min-h-dvh bg-[#f7f6f1] px-4 pb-28 pt-9">
        <header>
          <h1 className="text-[34px] font-bold tracking-[-0.04em]">今日素材</h1>
          <p className="mt-2 text-base text-[#8b9994]">{formatKindergartenToday()} · 今天拍的都在这里</p>
        </header>

        <button aria-label="上传素材" className="mt-5 flex min-h-16 w-full items-center justify-center gap-3 rounded-2xl bg-brand text-xl font-bold text-white shadow-[0_10px_25px_rgba(49,116,90,0.20)]" onClick={() => setSearchParams({ upload: "1" })} type="button">
          <Blocks aria-hidden className="shrink-0 text-brand-soft" size={24} strokeWidth={2} />
          <span className="text-left">
            上传素材
            <span className="block text-xs font-medium text-white/85">选择手机里拍好的照片或视频</span>
          </span>
        </button>

        <div className="mt-5">
          {isLoading && <p className="py-20 text-center text-sm text-ink-muted">正在看看今天的素材…</p>}
          {hasError && <button className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl border border-red-200 bg-red-50 text-sm font-medium text-red-700" onClick={() => void Promise.all([observations.refetch(), areas.refetch(), children.refetch(), media.refetch()])} type="button"><RotateCcw size={16} /> 加载失败，点这里重试</button>}
          {!isLoading && !hasError && todayRecords.length === 0 && (
            <section className="flex min-h-[48vh] flex-col items-center justify-center text-center">
              <div className="grid size-20 place-items-center rounded-[26px] bg-white text-brand shadow-sm"><ImageIcon aria-hidden size={34} /></div>
              <h2 className="mt-5 text-lg font-bold">今天还没有素材</h2>
              <p className="mt-2 text-sm text-ink-muted">拍完就点上面的按钮传上来</p>
            </section>
          )}
          <section aria-label="今日素材列表" className="space-y-3">
            {todayRecords.map((record) => <MaterialCard areaName={areaNames.get(record.area_id) ?? "未知区域"} childName={record.child_id == null ? "未指定幼儿" : childNames.get(record.child_id) ?? "幼儿信息待同步"} key={record.id} media={mediaByObservation.get(record.id)} record={record} />)}
          </section>
        </div>
      </div>
      <HomeTabBar active="today" />
      {uploadOpen && <UploadSheet onClose={closeUpload} onUploaded={(observationId) => navigate(`/observations/${observationId}/review`, { replace: true })} />}
    </MobilePage>
  );
}
