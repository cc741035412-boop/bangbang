import { ArrowLeft, Download, FileText, Image as ImageIcon, LoaderCircle, Pencil, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { MobilePage } from "../components/mobile-page";
import {
  getMediaFileUrl,
  getObservationExportUrl,
  useObservation,
  type ObservationTag,
} from "../features/observations/api";
import { formatKindergartenDateTime } from "../lib/date-time";

const AGE_GROUP_LABELS: Record<string, string> = {
  small: "小班",
  middle: "中班",
  large: "大班",
};

const LEVEL_LABELS: Record<number, string> = {
  1: "初阶",
  2: "中阶",
  3: "高阶",
};

export function ObservationDetailPage() {
  const { observationId } = useParams();
  const id = Number(observationId);
  const observation = useObservation(id);
  const [previewMediaId, setPreviewMediaId] = useState<number | null>(null);
  const [failedImages, setFailedImages] = useState<Set<number>>(new Set());
  const [includeIndicators, setIncludeIndicators] = useState(false);
  const record = observation.data;

  if (!Number.isInteger(id) || id <= 0) {
    return <DetailMessage title="找不到这条观察记录" />;
  }

  if (observation.isLoading) {
    return <DetailMessage loading title="正在打开观察记录…" />;
  }

  if (observation.isError || !record) {
    return <DetailMessage title="这条观察记录暂时打不开" />;
  }

  if (record.status !== "confirmed") {
    return (
      <DetailMessage title="这条记录还没有确认完成">
        <Link className="mt-6 rounded-2xl bg-brand px-5 py-3 font-bold text-white" to={`/observations/${id}/review`}>
          返回整理
        </Link>
      </DetailMessage>
    );
  }

  const systemTags = record.tags.filter((tag) => tag.source === "system_determined" && tag.accepted === true);
  const aiTags = record.tags.filter((tag) => tag.source === "ai_suggested" && tag.accepted === true);
  const teacherTags = record.tags.filter((tag) => tag.source === "teacher_added" && tag.accepted === true);
  const previewMedia = record.media.find((item) => item.id === previewMediaId);

  return (
    <MobilePage>
      <article className="min-h-dvh bg-[#f5f2ea] pb-48">
        <header className="border-b border-[#ddd7ca] bg-[#fffdf7] px-5 pb-7 pt-5">
          <Link
            aria-label="返回今日素材"
            className="mb-7 grid size-11 place-items-center rounded-full border border-stone-200 bg-white text-ink"
            to="/"
          >
            <ArrowLeft size={21} />
          </Link>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="mb-2 text-xs font-bold tracking-[0.2em] text-brand-deep">观察记录</p>
              <h1 className="text-[32px] font-bold leading-tight tracking-[-0.03em]">{record.child_name ?? "未指定幼儿"}</h1>
            </div>
            <span className="mt-1 shrink-0 rounded-full bg-emerald-100 px-3 py-1.5 text-sm font-bold text-emerald-800">已完成</span>
          </div>
          <p className="mt-4 text-[15px] leading-7 text-ink-muted">
            {record.area_name ?? "未知区域"} · {formatKindergartenDateTime(record.observed_at)} · {AGE_GROUP_LABELS[record.age_group] ?? record.age_group}
          </p>
        </header>

        <div className="space-y-10 px-5 py-8">
          <section aria-labelledby="media-heading">
            <SectionHeading id="media-heading">素材</SectionHeading>
            <div className="mt-4 space-y-4">
              {record.media.map((media) => {
                const isVideo = media.content_type.startsWith("video/");
                if (isVideo) {
                  return (
                    <video
                      className="aspect-video w-full rounded-2xl bg-black object-contain shadow-sm"
                      controls
                      key={media.id}
                      playsInline
                      preload="metadata"
                      src={getMediaFileUrl(media.id)}
                    >
                      当前浏览器无法播放这段视频。
                    </video>
                  );
                }

                return (
                  <button
                    aria-label="查看素材大图"
                    className="block aspect-[4/3] w-full overflow-hidden rounded-2xl bg-stone-200 shadow-sm"
                    key={media.id}
                    onClick={() => setPreviewMediaId(media.id)}
                    type="button"
                  >
                    {failedImages.has(media.id) ? (
                      <span className="grid size-full place-items-center text-stone-500"><ImageIcon size={34} /></span>
                    ) : (
                      <img
                        alt="观察素材"
                        className="size-full object-cover"
                        onError={() => setFailedImages((current) => new Set(current).add(media.id))}
                        src={getMediaFileUrl(media.id)}
                      />
                    )}
                  </button>
                );
              })}
              {record.media.length === 0 && <p className="text-stone-400">暂无素材</p>}
            </div>
          </section>

          <section aria-labelledby="record-heading" className="rounded-[28px] border border-[#dfd8ca] bg-[#fffdf8] px-5 py-6 shadow-[0_10px_30px_rgba(71,62,45,0.06)]">
            <div className="mb-7 flex items-center gap-3 border-b border-[#e8e2d6] pb-5">
              <span className="grid size-10 place-items-center rounded-full bg-brand-soft text-brand-deep"><FileText size={20} /></span>
              <h2 className="text-xl font-bold" id="record-heading">观察记录正文</h2>
            </div>
            <div className="space-y-9">
              <RecordSection title="观察目的" value={record.purpose} />
              <RecordSection title="客观白描" value={record.narrative} />
              <RecordSection title="分析" value={record.analysis} />
              <RecordSection title="措施" value={record.strategy} />
            </div>
          </section>

          <section aria-labelledby="tags-heading">
            <SectionHeading id="tags-heading">本条记录关联的指标</SectionHeading>
            <div className="mt-4 space-y-4">
              <IndicatorGroup className="border-stone-300 bg-stone-100" emptyText="无系统判定" label="系统判定（纯计算）" tags={systemTags} />
              <IndicatorGroup className="border-indigo-200 bg-indigo-50" emptyText="未采纳 AI 建议" label="AI 建议且教师采纳" tags={aiTags} />
              <IndicatorGroup className="border-emerald-200 bg-emerald-50" emptyText="教师未补充指标" label="教师自己补充" tags={teacherTags} />
            </div>
          </section>

          <p className="rounded-2xl border border-brand/20 bg-brand-soft px-4 py-4 text-center text-base font-bold text-brand-deep">
            {record.child_name ?? "这位幼儿"} · 本学期第 {record.child_confirmed_count} 条观察记录
          </p>
        </div>
      </article>

      <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200/70 bg-[#f5f2ea]/95 px-5 pt-3">
        <label className="mb-2 flex min-h-8 items-center justify-end gap-2 text-sm text-ink-muted">
          <input
            checked={includeIndicators}
            className="size-4 accent-brand"
            onChange={(event) => setIncludeIndicators(event.target.checked)}
            type="checkbox"
          />
          附带指标
        </label>
        <div className="grid grid-cols-2 gap-3">
          <Link className="flex min-h-14 items-center justify-center gap-2 rounded-2xl border border-brand bg-white font-bold text-brand-deep" to={`/observations/${id}/review`}>
            <Pencil size={18} /> 继续编辑
          </Link>
          <a
            className="flex min-h-14 items-center justify-center gap-2 rounded-2xl bg-brand font-bold text-white"
            download
            href={getObservationExportUrl(id, includeIndicators)}
          >
            <Download size={18} /> 导出这条
          </a>
        </div>
      </div>

      {previewMedia && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/90 p-3" role="dialog" aria-label="素材大图" aria-modal="true">
          <button
            aria-label="关闭大图"
            className="absolute right-4 top-4 grid size-11 place-items-center rounded-full bg-white/15 text-white"
            onClick={() => setPreviewMediaId(null)}
            type="button"
          >
            <X size={24} />
          </button>
          <img alt="观察素材大图" className="max-h-full max-w-full object-contain" src={getMediaFileUrl(previewMedia.id)} />
        </div>
      )}
    </MobilePage>
  );
}

function SectionHeading({ children, id }: { children: ReactNode; id: string }) {
  return <h2 className="text-xl font-bold tracking-[-0.02em]" id={id}>{children}</h2>;
}

function RecordSection({ title, value }: { title: string; value?: string | null }) {
  return (
    <section>
      <h3 className="mb-3 text-sm font-bold tracking-[0.12em] text-brand-deep">{title}</h3>
      <p className={`whitespace-pre-wrap text-[17px] leading-8 ${value?.trim() ? "text-ink" : "text-stone-400"}`}>
        {value?.trim() || "未填写"}
      </p>
    </section>
  );
}

function IndicatorGroup({ className, emptyText, label, tags }: {
  className: string;
  emptyText: string;
  label: string;
  tags: ObservationTag[];
}) {
  return (
    <section className={`rounded-2xl border p-4 ${className}`}>
      <h3 className="text-sm font-bold">{label}</h3>
      <div className="mt-3 space-y-2">
        {tags.map((tag) => (
          <div className="flex items-center justify-between gap-3 rounded-xl bg-white/80 px-3 py-3" key={tag.id}>
            <span className="font-bold">{tag.indicator_code} {tag.indicator_name}</span>
            <span className="shrink-0 text-sm font-bold text-ink-muted">{LEVEL_LABELS[tag.level] ?? `第 ${tag.level} 阶`}</span>
          </div>
        ))}
        {tags.length === 0 && <p className="text-sm text-stone-500">{emptyText}</p>}
      </div>
    </section>
  );
}

function DetailMessage({ children, loading = false, title }: { children?: ReactNode; loading?: boolean; title: string }) {
  return (
    <MobilePage>
      <div className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
        {loading && <LoaderCircle aria-hidden className="mb-4 animate-spin text-brand" size={32} />}
        <h1 className="text-xl font-bold">{title}</h1>
        {children}
        <Link className="mt-6 flex min-h-11 items-center px-5 font-bold text-brand" to="/">返回今日素材</Link>
      </div>
    </MobilePage>
  );
}
