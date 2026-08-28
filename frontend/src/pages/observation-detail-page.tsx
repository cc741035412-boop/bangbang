import { ArrowDown, ArrowLeft, Download, FileText, Home, LoaderCircle, Share2, X } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { MobilePage } from "../components/mobile-page";
import { ExportFormatSheet } from "../components/export-format-sheet";
import {
  fetchObservationExportAs,
  firstEnabledFormat,
  formatFileSize,
  formatOption,
  triggerBrowserDownload,
  type ExportedFile,
  type ExportFormat,
} from "../features/exports/api";
import {
  useIndicators,
  useObservation,
  type ObservationTag,
} from "../features/observations/api";
import { formatKindergartenDateTime } from "../lib/date-time";

const DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric", month: "long", day: "numeric", timeZone: "Asia/Shanghai",
});

export function ObservationDetailPage() {
  const { observationId } = useParams();
  const id = Number(observationId);
  const observation = useObservation(id);
  const indicators = useIndicators();
  const [exportOpen, setExportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [exportedFile, setExportedFile] = useState<ExportedFile | null>(null);
  const [selectedFormat, setSelectedFormat] = useState<ExportFormat | null>(firstEnabledFormat());
  const record = observation.data;
  const dimensions = useMemo(
    () => new Map(indicators.data?.map((item) => [item.indicator_code, item.dimension]) ?? []),
    [indicators.data],
  );

  if (!Number.isInteger(id) || id <= 0) return <DetailMessage title="找不到这条观察记录" />;
  if (observation.isLoading) return <DetailMessage loading title="正在打开观察记录…" />;
  if (observation.isError || !record) return <DetailMessage title="这条观察记录暂时打不开" />;
  if (record.status !== "confirmed") {
    return (
      <DetailMessage title="这条记录还没有确认完成">
        <Link className="mt-6 rounded-2xl bg-brand px-5 py-3 font-bold text-white" to={`/observations/${id}/review`}>返回整理</Link>
      </DetailMessage>
    );
  }
  if (exportedFile) {
    return <ExportSuccessView exportedFile={exportedFile} onDownload={() => triggerBrowserDownload(exportedFile)} />;
  }

  const acceptedTags = record.tags.filter((tag) => tag.accepted === true);
  const observedDate = DATE_FORMATTER.format(new Date(record.observed_at));
  const duration = formatDuration(record.media.reduce((sum, media) => sum + (media.duration_sec ?? 0), 0));

  async function runExport() {
    if (!selectedFormat) return;
    setExporting(true);
    setExportError("");
    try {
      const file = await fetchObservationExportAs(id, selectedFormat, true);
      triggerBrowserDownload(file);
      setExportOpen(false);
      setExportedFile(file);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "这次导出没有成功，请重试");
    } finally {
      setExporting(false);
    }
  }

  return (
    <MobilePage>
      <article className="min-h-dvh bg-[#f7f6f1] pb-36">
        <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-stone-200/80 bg-[#f7f6f1]/95 px-5 backdrop-blur">
          <Link aria-label="返回首页" className="grid size-10 place-items-center text-ink-muted" to="/"><ArrowLeft size={22} /></Link>
          <h1 className="text-xl font-bold">完整稿</h1>
          <span className="w-10 text-right text-sm text-ink-muted">已保存</span>
        </header>

        <div className="px-4 py-4">
          <div className="rounded-[22px] border border-[#ddd9cf] bg-white px-5 py-8 shadow-[0_2px_10px_rgba(36,37,32,0.04)]">
            <div className="text-center">
              <h2 className="text-[26px] font-bold tracking-[-0.03em]">{record.child_name ?? "未指定幼儿"}的观察记录</h2>
              <p className="mt-3 text-sm text-[#8a9792]">{observedDate} · {record.area_name ?? "未填写区域"}</p>
            </div>
            <div className="my-6 border-t border-[#e5e1d8]" />

            <dl className="grid grid-cols-[76px_1fr] gap-y-2 rounded-2xl bg-[#faf9f5] px-4 py-4 text-[15px] leading-7">
              <dt className="font-bold">幼儿</dt><dd className="text-ink-muted">{record.child_name ?? "未指定"}{record.classroom_name ? `（${record.classroom_name}）` : ""}</dd>
              <dt className="font-bold">观察者</dt><dd className="text-ink-muted">{record.observer?.name ?? "未填写"}</dd>
              <dt className="font-bold">时间</dt><dd className="text-ink-muted">{formatKindergartenDateTime(record.observed_at)}{duration ? ` · 时长 ${duration}` : ""}</dd>
              <dt className="font-bold">场景</dt><dd className="text-ink-muted">{record.area_name ?? "未填写区域"}{record.location ? ` · ${record.location}` : " · 自主游戏"}</dd>
            </dl>

            <DocumentSection title="观察目的"><DocumentText value={record.purpose} /></DocumentSection>
            <DocumentSection title="观察记录"><DocumentText value={record.narrative} /></DocumentSection>
            <DocumentSection title="观察分析">
              <div className="space-y-5">
                {acceptedTags.map((tag, index) => <AcceptedIndicator dimension={dimensions.get(tag.indicator_code)} index={index} key={tag.id} tag={tag} />)}
                {acceptedTags.length === 0 && <p className="text-stone-400">未采纳观察指标</p>}
                <DocumentText value={record.analysis} />
              </div>
            </DocumentSection>
            <DocumentSection title="下一步支持策略"><DocumentText value={record.strategy} /></DocumentSection>

            <div className="mt-8 border-t border-dashed border-[#ddd9cf] pt-5 text-right text-sm leading-7 text-[#8a9792]">
              <p>记录人：{record.observer?.name ?? "未填写"}</p><p>{observedDate}</p>
            </div>
          </div>
          <p className="py-5 text-center text-sm text-[#94a09b]">共 {acceptedTags.length} 条采纳指标 · 导出后可继续编辑</p>
        </div>
      </article>

      <div className="safe-bottom fixed inset-x-0 bottom-0 z-20 mx-auto grid w-full max-w-[430px] grid-cols-[1fr_1.7fr] gap-3 border-t border-stone-200 bg-[#f7f6f1]/95 px-4 pt-3 backdrop-blur">
        <Link className="flex min-h-14 items-center justify-center rounded-2xl border border-[#dedbd2] bg-white font-bold text-ink-muted" to={`/observations/${id}/review`}>返回编辑</Link>
        <button className="min-h-14 rounded-2xl bg-brand font-bold text-white" onClick={() => setExportOpen(true)} type="button">导出</button>
      </div>

      {exportOpen && (
        <ExportFormatSheet
          error={exportError}
          exporting={exporting}
          onClose={() => { if (!exporting) setExportOpen(false); }}
          onExport={() => void runExport()}
          onSelect={setSelectedFormat}
          selected={selectedFormat}
        />
      )}
    </MobilePage>
  );
}

function DocumentSection({ children, title }: { children: ReactNode; title: string }) {
  return <section className="mt-7"><h3 className="mb-3 border-l-4 border-brand pl-3 text-lg font-bold">{title}</h3>{children}</section>;
}

function DocumentText({ value }: { value?: string | null }) {
  return <p className={`whitespace-pre-wrap text-[16px] leading-8 ${value?.trim() ? "text-ink" : "text-stone-400"}`}>{value?.trim() || "未填写"}</p>;
}

function AcceptedIndicator({ dimension, index, tag }: { dimension?: string; index: number; tag: ObservationTag }) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 font-bold"><span>{index + 1}. {tag.indicator_name}</span>{dimension && <span className="rounded bg-[#efeee9] px-2 py-0.5 text-xs font-normal text-ink-muted">{dimension}</span>}</div>
      {tag.ai_reason?.trim() && <p className="mt-3 border-l-2 border-[#c9e2d6] bg-[#faf9f5] px-3 py-2 text-sm leading-6 text-ink-muted">推荐依据：{tag.ai_reason}</p>}
    </div>
  );
}

function ExportSuccessView({ exportedFile, onDownload }: { exportedFile: ExportedFile; onDownload: () => void }) {
  const option = formatOption(exportedFile.format);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareError, setShareError] = useState("");
  const file = useMemo(() => new File([exportedFile.blob], exportedFile.fileName, { type: exportedFile.blob.type }), [exportedFile]);
  const canShareFile = typeof navigator.share === "function" && (typeof navigator.canShare !== "function" || navigator.canShare({ files: [file] }));

  async function systemShare() {
    if (!canShareFile) return;
    setShareError("");
    try {
      await navigator.share({ files: [file], title: exportedFile.fileName });
      setShareOpen(false);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setShareError("系统分享没有完成，可以再次尝试或保存文件");
    }
  }

  return (
    <MobilePage>
      <div className="relative flex min-h-dvh flex-col overflow-hidden bg-[#f7f6f1] px-5">
        <Confetti />
        <div className="relative z-10 flex flex-1 flex-col items-center justify-center pb-28">
          <div className="w-full rounded-[24px] border border-[#dedbd2] bg-white p-5 shadow-[0_14px_35px_rgba(45,54,48,0.10)]">
            <span className={`grid size-14 place-items-center rounded-xl text-lg font-bold text-white ${option.color}`}>{option.label}</span>
            <h1 className="mt-4 break-all text-xl font-bold">{exportedFile.fileName}</h1>
            <p className="mt-2 text-base text-[#8a9792]">{option.name} · {formatFileSize(exportedFile.size)}</p>
            <div className="mt-5 space-y-2 border-t border-[#e3dfd7] pt-4"><span className="block h-2 w-full rounded bg-[#efeee9]" /><span className="block h-2 w-4/5 rounded bg-[#efeee9]" /><span className="block h-2 w-3/5 rounded bg-[#efeee9]" /></div>
          </div>
          <div className="mt-8 flex items-center gap-3 text-[28px] font-bold text-brand"><span aria-hidden>🎉</span><span>导出成功！</span></div>
          <p className="mt-3 text-center text-base text-[#8a9792]">已下载到浏览器默认下载位置</p>
          <p className="mt-9 text-lg text-ink-muted">分享</p>
          <button aria-label={`分享导出的 ${option.name}`} className="mt-3 grid size-14 place-items-center rounded-full border border-[#dfdcd4] bg-white text-brand shadow-sm" onClick={() => setShareOpen(true)} type="button"><ArrowDown size={24} /></button>
        </div>
        <div className="safe-bottom relative z-10 flex justify-end pb-2"><Link className="flex min-h-12 items-center gap-2 rounded-full border border-[#dedbd2] bg-white px-6 font-medium text-ink-muted" to="/"><Home size={18} /> 返回首页</Link></div>

        {shareOpen && (
          <div aria-label="分享文件" aria-modal="true" className="fixed inset-0 z-40 flex items-end justify-center bg-black/35" role="dialog">
            <button aria-label="关闭分享" className="absolute inset-0" onClick={() => setShareOpen(false)} type="button" />
            <section className="safe-bottom relative z-10 w-full max-w-[430px] rounded-t-[28px] bg-white px-5 pb-2 pt-6">
              <div className="flex items-start justify-between"><div><h2 className="text-2xl font-bold">分享文件</h2><p className="mt-2 text-sm leading-6 text-ink-muted">由系统分享面板决定可用的应用；网页不能直接指定微信或 QQ。</p></div><button aria-label="关闭" className="grid size-9 place-items-center text-ink-muted" onClick={() => setShareOpen(false)} type="button"><X size={21} /></button></div>
              <div className="mt-5 grid grid-cols-2 gap-3">
                <button className="flex min-h-24 flex-col items-center justify-center gap-2 rounded-2xl border border-[#dedbd2] disabled:opacity-40" disabled={!canShareFile} onClick={() => void systemShare()} type="button"><Share2 className="text-brand" size={25} /><span className="font-bold">系统分享</span></button>
                <button className="flex min-h-24 flex-col items-center justify-center gap-2 rounded-2xl border border-[#dedbd2]" onClick={onDownload} type="button"><Download className="text-brand" size={25} /><span className="font-bold">再次下载</span></button>
              </div>
              {!canShareFile && <p className="mt-3 text-sm text-ink-muted">当前浏览器不支持分享文件，可使用“再次下载”。</p>}
              {shareError && <p className="mt-3 text-sm text-red-700" role="alert">{shareError}</p>}
              <button className="mt-5 min-h-14 w-full rounded-2xl bg-[#f1f0eb] font-bold text-ink-muted" onClick={() => setShareOpen(false)} type="button">取消</button>
            </section>
          </div>
        )}
      </div>
    </MobilePage>
  );
}

function Confetti() {
  const pieces = [["12%", "25%", "bg-brand"], ["23%", "18%", "bg-[#e49585]"], ["78%", "26%", "bg-[#d29a45]"], ["86%", "38%", "bg-[#7fc5a7]"], ["18%", "48%", "bg-[#8fcab2]"], ["73%", "51%", "bg-[#e8c46a]"]];
  return <div aria-hidden className="pointer-events-none absolute inset-0">{pieces.map(([left, top, color], index) => <span className={`absolute h-2 w-3 rotate-12 ${color}`} key={index} style={{ left, top }} />)}</div>;
}

function formatDuration(totalSeconds: number) {
  if (totalSeconds <= 0) return "";
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes} 分 ${seconds} 秒` : `${seconds} 秒`;
}

function DetailMessage({ children, loading = false, title }: { children?: ReactNode; loading?: boolean; title: string }) {
  return (
    <MobilePage><div className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">{loading ? <LoaderCircle aria-hidden className="mb-4 animate-spin text-brand" size={32} /> : <FileText aria-hidden className="mb-4 text-brand" size={32} />}<h1 className="text-xl font-bold">{title}</h1>{children}<Link className="mt-6 flex min-h-11 items-center px-5 font-bold text-brand" to="/">返回今日素材</Link></div></MobilePage>
  );
}
