import { useQuery } from "@tanstack/react-query";

import { requestBlob, requestJson } from "../../api/http";
import { FEATURES } from "../../config/features";

export type ExportFormat = "docx" | "pdf" | "md";

export interface ExportFormatOption {
  format: ExportFormat;
  /** 卡片上的名字 */
  name: string;
  /** 写用途，不写格式名词——老师不需要懂格式区别 */
  description: string;
  /** 图标底色，沿用界面原有取色 */
  color: string;
  label: string;
  extension: string;
  enabled: boolean;
}

export const EXPORT_FORMATS: ExportFormatOption[] = [
  {
    format: "docx",
    name: "Word 文档",
    description: "可直接编辑、打印，交给园所存档",
    color: "bg-[#2b5797]",
    label: "W",
    extension: ".docx",
    enabled: FEATURES.exportDocx,
  },
  {
    format: "pdf",
    name: "PDF",
    description: "排版固定，适合发给家长看",
    color: "bg-[#c83b31]",
    label: "PDF",
    extension: ".pdf",
    enabled: FEATURES.exportPdf,
  },
  {
    format: "md",
    name: "Markdown",
    description: "纯文本，方便二次整理",
    color: "bg-[#60716b]",
    label: "MD",
    extension: ".md",
    enabled: FEATURES.exportMarkdown,
  },
];

export function firstEnabledFormat(): ExportFormat | null {
  return EXPORT_FORMATS.find((option) => option.enabled)?.format ?? null;
}

export function formatOption(format: ExportFormat) {
  return EXPORT_FORMATS.find((option) => option.format === format) ?? EXPORT_FORMATS[0];
}

export interface ExportedFile {
  blob: Blob;
  fileName: string;
  size: number;
  format: ExportFormat;
}

/**
 * 单篇导出。
 * 后端约定：format 作为查询参数，docx 保持现有行为不变，pdf/md 新增。
 * 导出成功后由后端自己写一条导出历史，前端不再单独上报——否则下载失败也会留下记录。
 */
export async function fetchObservationExportAs(
  observationId: number,
  format: ExportFormat,
  includeIndicators = true,
): Promise<ExportedFile> {
  const query = new URLSearchParams({
    include_indicators: String(includeIndicators),
    format,
  });
  const { blob, fileName } = await requestBlob(
    `/observations/${observationId}/export?${query.toString()}`,
    `${formatOption(format).name}暂时没有导出成功`,
  );
  return { blob, fileName, size: blob.size, format };
}

export function getMonthlyExportUrlAs(
  year: number,
  month: number,
  format: ExportFormat,
  includeIndicators = true,
) {
  const params = new URLSearchParams({
    year: String(year),
    month: String(month),
    include_indicators: String(includeIndicators),
    format,
  });
  return `/api/exports/monthly?${params.toString()}`;
}

export interface ExportRecord {
  id: number;
  observation_id: number | null;
  /** single = 单篇导出，monthly = 整月合并导出 */
  scope: "single" | "monthly";
  format: ExportFormat;
  file_name: string;
  size: number;
  child_name: string | null;
  created_at: string;
  /** 后端保留文件时给下载地址；不保留文件则为 null，前端展示「重新导出」 */
  download_url: string | null;
}

const exportKeys = { history: ["exports", "history"] as const };

export function useExportHistory() {
  return useQuery({
    queryKey: exportKeys.history,
    queryFn: () =>
      requestJson<ExportRecord[]>("/exports/history", {
        method: "GET",
        fallbackMessage: "导出记录加载失败",
      }),
    enabled: FEATURES.exportHistory,
  });
}

export function triggerBrowserDownload(file: { blob: Blob; fileName: string }) {
  const url = URL.createObjectURL(file.blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.fileName;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
