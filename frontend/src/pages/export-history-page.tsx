import { Download, FileText, RefreshCw } from "lucide-react";
import { Link, Navigate } from "react-router";

import { MobilePage } from "../components/mobile-page";
import { FEATURES } from "../config/features";
import {
  formatFileSize,
  formatOption,
  useExportHistory,
  type ExportRecord,
} from "../features/exports/api";
import { PageHeader } from "./account-page";

const TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "Asia/Shanghai",
});

export function ExportHistoryPage() {
  const history = useExportHistory();

  if (!FEATURES.exportHistory) return <Navigate replace to="/mine" />;

  const records = history.data ?? [];

  return (
    <MobilePage>
      <main className="min-h-dvh bg-[#f7f6f1] px-5 pb-16 pt-5">
        <PageHeader subtitle="导出过的文件都留在这里" title="导出记录" />

        {history.isLoading && <p className="mt-7 text-sm text-ink-muted">正在加载导出记录…</p>}
        {history.isError && (
          <p className="mt-7 rounded-xl bg-red-50 px-3 py-3 text-sm text-red-700">
            导出记录加载失败，请刷新页面重试
          </p>
        )}

        {history.isSuccess && records.length === 0 && (
          <div className="mt-16 text-center text-sm leading-7 text-ink-muted">
            <FileText aria-hidden className="mx-auto mb-4 text-brand" size={32} />
            还没有导出过文件
            <br />
            生成完整稿后点导出，文件会留在这里
          </div>
        )}

        {records.length > 0 && (
          <>
            <p className="mt-6 text-sm text-ink-muted">共 {records.length} 个文件 · 最新的在最上面</p>
            <ul className="mt-3 space-y-3">
              {records.map((record) => (
                <ExportRow key={record.id} record={record} />
              ))}
            </ul>
          </>
        )}
      </main>
    </MobilePage>
  );
}

function ExportRow({ record }: { record: ExportRecord }) {
  const option = formatOption(record.format);
  return (
    <li className="flex items-center gap-3 rounded-2xl border border-[#dfdcd4] bg-white p-3">
      <span
        className={`grid size-11 shrink-0 place-items-center rounded-xl text-xs font-bold text-white ${option.color}`}
      >
        {option.label}
      </span>
      <span className="min-w-0 flex-1">
        <strong className="block truncate text-[15px]">{record.file_name}</strong>
        <span className="mt-1 block text-xs text-[#8b9994]">
          {TIME_FORMATTER.format(new Date(record.created_at))} · {formatFileSize(record.size)}
          {record.scope === "monthly" && " · 整月合并"}
        </span>
      </span>
      {record.download_url ? (
        <a
          className="shrink-0 rounded-full border border-[#c9e2d6] px-3 py-2 text-xs font-medium text-brand"
          download={record.file_name}
          href={record.download_url}
        >
          <Download aria-hidden className="inline" size={14} /> 下载
        </a>
      ) : record.observation_id ? (
        <Link
          className="shrink-0 rounded-full border border-[#c9e2d6] px-3 py-2 text-xs font-medium text-brand"
          to={`/observations/${record.observation_id}`}
        >
          <RefreshCw aria-hidden className="inline" size={14} /> 重新导出
        </Link>
      ) : null}
    </li>
  );
}
