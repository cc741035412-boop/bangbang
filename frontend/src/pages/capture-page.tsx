import { ArrowLeft, FileVideo, ImagePlus } from "lucide-react";
import { type ChangeEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { MobilePage } from "../components/mobile-page";
import {
  CaptureError,
  MAX_UPLOAD_SIZE_BYTES,
  useAreas,
  useSubmitCapture,
} from "../features/observations/api";

const SUPPORTED_FILE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/heic",
  "image/heif",
  "video/mp4",
  "video/quicktime",
]);
const SUPPORTED_FILE_EXTENSIONS = new Set([
  ".jpg",
  ".jpeg",
  ".png",
  ".heic",
  ".heif",
  ".mp4",
  ".mov",
]);
const FILE_TOO_LARGE_MESSAGE = "文件太大了，最多 200MB。可以拍短一点的视频";
const FILE_TYPE_MESSAGE = "只支持照片和视频（JPG、PNG、HEIC、MP4、MOV）";

function isSupportedFile(file: File) {
  const normalizedType = file.type.split(";", 1)[0].trim().toLowerCase();
  if (SUPPORTED_FILE_TYPES.has(normalizedType)) return true;
  if (normalizedType !== "" && normalizedType !== "application/octet-stream") return false;
  const lastDot = file.name.lastIndexOf(".");
  const suffix = lastDot >= 0 ? file.name.slice(lastDot).toLowerCase() : "";
  return SUPPORTED_FILE_EXTENSIONS.has(suffix);
}

function isImageFile(file: File) {
  const lowerName = file.name.toLowerCase();
  return file.type.startsWith("image/")
    || lowerName.endsWith(".heic")
    || lowerName.endsWith(".heif");
}

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
  const [previewFailed, setPreviewFailed] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [uploadPercentage, setUploadPercentage] = useState<number | null>(null);
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
    previewUrlRef.current = selected && isImageFile(selected)
      ? URL.createObjectURL(selected)
      : null;
    setPreviewUrl(previewUrlRef.current);
    setPreviewFailed(false);
    setFile(selected);
    setFileError(
      selected == null
        ? null
        : !isSupportedFile(selected)
          ? FILE_TYPE_MESSAGE
          : selected.size > MAX_UPLOAD_SIZE_BYTES
            ? FILE_TOO_LARGE_MESSAGE
            : null,
    );
    setUploadPercentage(null);
    progress.current = {};
    submitCapture.reset();
  }

  function selectArea(id: number) {
    setAreaId(id);
    setUploadPercentage(null);
    progress.current = {};
    submitCapture.reset();
  }

  function submit() {
    if (!file || fileError || areaId == null || submitCapture.isPending) return;
    setUploadPercentage(0);
    submitCapture.mutate(
      {
        file,
        areaId,
        progress: progress.current,
        onUploadProgress: setUploadPercentage,
      },
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
  const canSubmit = file != null && fileError == null && areaId != null && !submitCapture.isPending;

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
            {previewUrl && !previewFailed ? (
              <div className="w-full">
                <img
                  alt="已选择图片预览"
                  className="h-52 w-full object-cover"
                  onError={() => setPreviewFailed(true)}
                  src={previewUrl}
                />
                <p className="px-4 py-3 text-sm text-ink-muted">{file?.name} · {formatFileSize(file?.size ?? 0)}</p>
              </div>
            ) : file ? (
              <div className="px-6 py-7">
                {isImageFile(file)
                  ? <ImagePlus aria-hidden className="mx-auto text-brand" size={38} strokeWidth={1.7} />
                  : <FileVideo aria-hidden className="mx-auto text-brand" size={38} strokeWidth={1.7} />}
                <p className="mt-3 max-w-[260px] truncate font-bold">{file.name}</p>
                <p className="mt-1 text-sm text-ink-muted">{formatFileSize(file.size)}</p>
              </div>
            ) : (
              <div className="px-6 py-7">
                <ImagePlus aria-hidden className="mx-auto text-brand" size={38} strokeWidth={1.7} />
                <p className="mt-3 font-bold">点这里选择文件</p>
                <p className="mt-1 text-sm text-ink-muted">JPG、PNG、HEIC、MP4 或 MOV，最多 200MB</p>
              </div>
            )}
            <input
              accept="image/jpeg,image/png,image/heic,image/heif,video/mp4,video/quicktime,.jpg,.jpeg,.png,.heic,.heif,.mp4,.mov"
              className="sr-only"
              onChange={selectFile}
              type="file"
            />
          </label>
          {fileError && <p className="mt-3 rounded-2xl bg-red-50 px-4 py-3 text-sm font-bold text-red-700">{fileError}</p>}
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

        {submitCapture.isPending && uploadPercentage != null && (
          <section aria-label="上传进度" className="mt-6 rounded-2xl bg-brand-soft px-4 py-3">
            <div className="flex items-center justify-between text-sm font-bold text-brand-deep">
              <span>{uploadPercentage < 100 ? "正在上传…" : "正在保存记录…"}</span>
              <span>{uploadPercentage}%</span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/80">
              <div
                className="h-full rounded-full bg-brand"
                style={{ width: `${uploadPercentage}%` }}
              />
            </div>
          </section>
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
