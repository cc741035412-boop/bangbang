import { ArrowLeft, FileVideo, ImagePlus } from "lucide-react";
import { type ChangeEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { MobilePage } from "../components/mobile-page";
import { CaptureError, useAreas, useSubmitCapture } from "../features/observations/api";

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function CapturePage() {
  const navigate = useNavigate();
  const enteredAt = useRef<number | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const progress = useRef<{ mediaId?: number; observationId?: number }>({});
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [areaId, setAreaId] = useState<number | null>(null);
  const areas = useAreas();
  const submitCapture = useSubmitCapture();

  useEffect(() => {
    enteredAt.current = performance.now();
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = selected?.type.startsWith("image/")
      ? URL.createObjectURL(selected)
      : null;
    setPreviewUrl(previewUrlRef.current);
    setFile(selected);
    progress.current = {};
    submitCapture.reset();
  }

  function selectArea(id: number) {
    setAreaId(id);
    progress.current = {};
    submitCapture.reset();
  }

  function submit() {
    if (!file || areaId == null || submitCapture.isPending) return;
    submitCapture.mutate(
      { file, areaId, progress: progress.current },
      {
        onSuccess: () => {
          const duration = (performance.now() - (enteredAt.current ?? performance.now())) / 1000;
          console.log(`[capture-duration] ${duration.toFixed(1)}s`);
          navigate("/", { replace: true, state: { captureDuration: duration } });
        },
      },
    );
  }

  const errorMessage = submitCapture.error instanceof CaptureError
    ? submitCapture.error.message
    : submitCapture.isError ? "上传失败，点这里重试" : null;
  const canSubmit = file != null && areaId != null && !submitCapture.isPending;

  return (
    <MobilePage>
      <div className="px-5 pb-32 pt-5">
        <header className="mb-7 flex items-center gap-3">
          <button aria-label="返回今日素材" className="grid size-11 place-items-center rounded-full bg-surface text-ink shadow-sm" onClick={() => navigate(-1)} type="button">
            <ArrowLeft aria-hidden size={21} />
          </button>
          <div>
            <h1 className="text-2xl font-bold tracking-[-0.02em]">快速沉淀</h1>
            <p className="mt-0.5 text-sm text-ink-muted">先存下来，稍后再整理</p>
          </div>
        </header>

        <section aria-labelledby="file-heading">
          <h2 className="mb-3 text-base font-bold" id="file-heading">1. 选择照片或视频</h2>
          <label className="flex min-h-40 cursor-pointer flex-col items-center justify-center overflow-hidden rounded-3xl border-2 border-dashed border-stone-300 bg-surface text-center">
            {previewUrl ? (
              <img alt="已选择图片预览" className="h-52 w-full object-cover" src={previewUrl} />
            ) : file ? (
              <div className="px-6 py-7">
                <FileVideo aria-hidden className="mx-auto text-brand" size={38} strokeWidth={1.7} />
                <p className="mt-3 max-w-[260px] truncate font-bold">{file.name}</p>
                <p className="mt-1 text-sm text-ink-muted">{formatFileSize(file.size)}</p>
              </div>
            ) : (
              <div className="px-6 py-7">
                <ImagePlus aria-hidden className="mx-auto text-brand" size={38} strokeWidth={1.7} />
                <p className="mt-3 font-bold">点这里选择文件</p>
                <p className="mt-1 text-sm text-ink-muted">JPG、PNG 或 MP4，最多 20MB</p>
              </div>
            )}
            <input accept="image/jpeg,image/png,video/mp4" className="sr-only" onChange={selectFile} type="file" />
          </label>
        </section>

        <section className="mt-7" aria-labelledby="area-heading">
          <h2 className="mb-3 text-base font-bold" id="area-heading">2. 选择所在区域</h2>
          {areas.isLoading && <p className="text-sm text-ink-muted">正在加载区域…</p>}
          {areas.isError && (
            <button className="min-h-11 text-sm font-bold text-red-700" onClick={() => void areas.refetch()} type="button">
              区域加载失败，点这里重试
            </button>
          )}
          <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-2" role="radiogroup" aria-label="游戏区域">
            {(areas.data ?? []).map((area) => (
              <button
                aria-checked={areaId === area.id}
                className={`min-h-11 shrink-0 rounded-full border px-5 text-sm font-bold ${areaId === area.id ? "border-brand bg-brand text-white" : "border-stone-300 bg-surface text-ink-muted"}`}
                key={area.id}
                onClick={() => selectArea(area.id)}
                role="radio"
                type="button"
              >
                {area.name}
              </button>
            ))}
          </div>
        </section>

        {errorMessage && (
          <button className="mt-6 w-full rounded-2xl bg-red-50 px-4 py-3 text-left text-sm font-bold text-red-700" onClick={submit} type="button">
            {errorMessage}
          </button>
        )}
      </div>

      <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200/70 bg-canvas/95 px-5 pt-3">
        <button
          className="min-h-14 w-full rounded-2xl bg-brand text-lg font-bold text-white shadow-[0_8px_24px_rgba(45,105,80,0.22)] disabled:bg-stone-300 disabled:text-stone-500 disabled:shadow-none"
          disabled={!canSubmit}
          onClick={submit}
          type="button"
        >
          {submitCapture.isPending ? "正在存下…" : "先存下来"}
        </button>
      </div>
    </MobilePage>
  );
}
