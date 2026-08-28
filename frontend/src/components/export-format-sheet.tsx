import { Download, LoaderCircle, X } from "lucide-react";

import { EXPORT_FORMATS, type ExportFormat } from "../features/exports/api";

/**
 * 导出格式选择弹层。
 *
 * 未接入的格式置灰并标「暂未开放」，不可选中，也不会发请求。
 * codex：后端做好 PDF / Markdown 后，把 src/config/features.ts 里对应的开关改成 true 即可，
 * 本组件不用动。
 */
export function ExportFormatSheet({
  error,
  exporting,
  onClose,
  onExport,
  onSelect,
  selected,
}: {
  error: string;
  exporting: boolean;
  onClose: () => void;
  onExport: () => void;
  onSelect: (format: ExportFormat) => void;
  selected: ExportFormat | null;
}) {
  const enabledCount = EXPORT_FORMATS.filter((option) => option.enabled).length;

  return (
    <div
      aria-label="导出格式"
      aria-modal="true"
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/35"
      role="dialog"
    >
      <button aria-label="关闭导出格式" className="absolute inset-0" onClick={onClose} type="button" />
      <section className="safe-bottom relative z-10 w-full max-w-[430px] rounded-t-[28px] bg-white px-5 pb-2 pt-6">
        <div className="mb-5 flex items-start justify-between">
          <div>
            <h2 className="text-2xl font-bold">导出格式</h2>
            <p className="mt-1 text-sm text-ink-muted">
              {enabledCount > 1 ? "选一个用途最合适的" : "当前支持导出 Word 文档"}
            </p>
          </div>
          <button
            aria-label="关闭"
            className="grid size-9 place-items-center text-ink-muted"
            disabled={exporting}
            onClick={onClose}
            type="button"
          >
            <X size={21} />
          </button>
        </div>

        {EXPORT_FORMATS.map((option) => {
          const isSelected = option.enabled && option.format === selected;
          return (
            <button
              aria-disabled={!option.enabled}
              aria-pressed={isSelected}
              className={`mb-3 flex w-full items-center gap-4 rounded-2xl border p-4 text-left ${
                isSelected ? "border-brand bg-[#edf6f1]" : "border-[#e2dfd7] bg-white"
              } ${option.enabled ? "" : "opacity-50"}`}
              disabled={!option.enabled || exporting}
              key={option.format}
              onClick={() => onSelect(option.format)}
              type="button"
            >
              <span
                className={`grid size-12 shrink-0 place-items-center rounded-xl text-sm font-bold text-white ${
                  option.enabled ? option.color : "bg-[#b3bab6]"
                }`}
              >
                {option.label}
              </span>
              <span className="min-w-0 flex-1">
                <strong className="block text-lg">{option.name}</strong>
                <span className="mt-0.5 block text-sm text-ink-muted">{option.description}</span>
              </span>
              {option.enabled ? (
                <span
                  className={`grid size-6 shrink-0 place-items-center rounded-full border-2 ${
                    isSelected ? "border-brand" : "border-stone-300"
                  }`}
                >
                  {isSelected && <span className="size-3 rounded-full bg-brand" />}
                </span>
              ) : (
                <span className="shrink-0 rounded bg-[#efeee9] px-2 py-1 text-xs text-ink-muted">
                  暂未开放
                </span>
              )}
            </button>
          );
        })}

        {error && (
          <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            {error}
          </p>
        )}

        <div className="mt-5 grid grid-cols-[1fr_2fr] gap-3">
          <button
            className="min-h-14 rounded-2xl bg-[#f1f0eb] font-bold text-ink-muted"
            disabled={exporting}
            onClick={onClose}
            type="button"
          >
            取消
          </button>
          <button
            className="flex min-h-14 items-center justify-center gap-2 rounded-2xl bg-brand font-bold text-white disabled:opacity-60"
            disabled={exporting || selected === null}
            onClick={onExport}
            type="button"
          >
            {exporting ? <LoaderCircle className="animate-spin" size={19} /> : <Download size={19} />}
            {exporting ? "正在生成…" : "确认导出"}
          </button>
        </div>
      </section>
    </div>
  );
}
