import { FileVideo, Image as ImageIcon, LoaderCircle, Paperclip, X } from "lucide-react";
import { type ChangeEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { FEATURES } from "../config/features";
import {
  CaptureError,
  MAX_UPLOAD_SIZE_BYTES,
  useAreas,
  useChildren,
  useSubmitCapture,
} from "../features/observations/api";

const ACCEPTED_VIDEO = "video/mp4,video/quicktime,.mp4,.mov";
const ACCEPTED_IMAGE = "image/jpeg,image/png,image/heic,image/heif,.jpg,.jpeg,.png,.heic,.heif";
const SUPPORTED_TYPES = new Set(["image/jpeg", "image/png", "image/heic", "image/heif", "video/mp4", "video/quicktime"]);
const SUPPORTED_SUFFIXES = new Set([".jpg", ".jpeg", ".png", ".heic", ".heif", ".mp4", ".mov"]);

export function UploadSheet({ onClose, onUploaded }: { onClose: () => void; onUploaded: (duration: number) => void }) {
  const enteredAt = useRef(0);
  const progress = useRef<{ mediaId?: number; observationId?: number }>({});
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const [areaId, setAreaId] = useState<number | null>(null);
  const [childId, setChildId] = useState<number | null>(null);
  // 多人游戏时额外勾选的幼儿；单选模式下始终为空
  const [extraChildIds, setExtraChildIds] = useState<number[]>([]);
  const [uploadPercentage, setUploadPercentage] = useState<number | null>(null);
  const areas = useAreas();
  const children = useChildren();
  const submitCapture = useSubmitCapture();

  useEffect(() => {
    enteredAt.current = performance.now();
  }, []);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    event.target.value = "";
    setFile(selected);
    setFileError(selected ? validateFile(selected) : "");
    setUploadPercentage(null);
    progress.current = {};
    submitCapture.reset();
  }

  /**
   * 单选模式：直接换主幼儿。
   * 多选模式：第一个选中的当主角；取消主角时，把下一个已选的顶上来，
   * 保证「主角」这个位置永远有人，后端的 child_id 不会变成 null。
   */
  function toggleChild(id: number) {
    if (!FEATURES.multiChildCapture) {
      setChildId(id);
      return;
    }
    if (childId === id) {
      const [next, ...rest] = extraChildIds;
      setChildId(next ?? null);
      setExtraChildIds(rest);
      return;
    }
    if (extraChildIds.includes(id)) {
      setExtraChildIds(extraChildIds.filter((item) => item !== id));
      return;
    }
    if (childId == null) setChildId(id);
    else setExtraChildIds([...extraChildIds, id]);
  }

  function submit() {
    if (!file || fileError || areaId == null || childId == null || submitCapture.isPending) return;
    setUploadPercentage(0);
    submitCapture.mutate(
      { file, areaId, childId, extraChildIds, progress: progress.current, onUploadProgress: setUploadPercentage },
      { onSuccess: () => onUploaded((performance.now() - enteredAt.current) / 1000) },
    );
  }

  const submitError = submitCapture.error instanceof CaptureError
    ? submitCapture.error.message
    : submitCapture.isError ? "上传失败，请重试" : "";
  const canSubmit = Boolean(file && !fileError && areaId != null && childId != null && !submitCapture.isPending);

  return (
    <div aria-label="上传素材" aria-modal="true" className="fixed inset-0 z-50 flex items-end justify-center bg-black/35" role="dialog">
      <button aria-label="关闭上传素材" className="absolute inset-0" disabled={submitCapture.isPending} onClick={onClose} type="button" />
      <section className="safe-bottom relative z-10 max-h-[92dvh] w-full max-w-[430px] overflow-y-auto rounded-t-[28px] bg-white px-5 pb-2 pt-6">
        <div className="flex items-start justify-between">
          <div><h2 className="text-2xl font-bold">上传素材</h2><p className="mt-2 text-sm leading-6 text-ink-muted">拍完就传，别攒到晚上。观察目的可在整理时补充。</p></div>
          <button aria-label="关闭" className="grid size-9 place-items-center text-ink-muted" disabled={submitCapture.isPending} onClick={onClose} type="button"><X size={21} /></button>
        </div>

        <StepCard number="1" title="选择文件">
          <div className="grid grid-cols-2 gap-3">
            <FileChoice accept={ACCEPTED_VIDEO} active={Boolean(file && isVideo(file))} icon={<FileVideo size={28} />} label="视频" onChange={chooseFile} />
            <FileChoice accept={ACCEPTED_IMAGE} active={Boolean(file && !isVideo(file))} icon={<ImageIcon size={28} />} label="照片" onChange={chooseFile} />
          </div>
          {file && (
            <div className="mt-3 flex min-h-12 items-center gap-3 rounded-xl bg-[#f7f6f2] px-3">
              <Paperclip aria-hidden className="shrink-0 text-brand" size={20} />
              <span className="min-w-0 flex-1 truncate text-sm">{file.name}</span>
              <button aria-label="移除所选文件" className="grid size-9 place-items-center text-ink-muted" disabled={submitCapture.isPending} onClick={() => { setFile(null); setFileError(""); }} type="button"><X size={19} /></button>
            </div>
          )}
          {fileError && <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{fileError}</p>}
        </StepCard>

        <StepCard number="2" title="游戏区域">
          <select aria-label="游戏区域" className="min-h-12 w-full rounded-xl border border-[#ddd9d0] bg-white px-3" disabled={areas.isLoading || submitCapture.isPending} onChange={(event) => setAreaId(event.target.value ? Number(event.target.value) : null)} value={areaId ?? ""}>
            <option value="">请选择游戏区域</option>
            {(areas.data ?? []).map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}
          </select>
          {areas.isError && <p className="mt-2 text-sm text-red-700">区域加载失败，请刷新后重试</p>}
        </StepCard>

        <StepCard number="3" title={FEATURES.multiChildCapture ? "这条素材里有哪些孩子" : "这是哪个孩子"}>
          <div
            aria-label="选择幼儿"
            className="flex flex-wrap gap-2"
            role={FEATURES.multiChildCapture ? "group" : "radiogroup"}
          >
            {(children.data ?? []).map((child) => {
              const isPrimary = childId === child.id;
              const isExtra = extraChildIds.includes(child.id);
              const selected = isPrimary || isExtra;
              return (
                <button
                  aria-checked={FEATURES.multiChildCapture ? undefined : isPrimary}
                  aria-pressed={FEATURES.multiChildCapture ? selected : undefined}
                  className={`min-h-11 rounded-full border px-5 ${selected ? "border-brand bg-[#eaf4ef] text-brand" : "border-[#ddd9d0] text-ink-muted"}`}
                  disabled={submitCapture.isPending}
                  key={child.id}
                  onClick={() => toggleChild(child.id)}
                  role={FEATURES.multiChildCapture ? undefined : "radio"}
                  type="button"
                >
                  {child.name}
                  {FEATURES.multiChildCapture && isPrimary && (
                    <span className="ml-1 text-xs">· 主角</span>
                  )}
                </button>
              );
            })}
          </div>
          {FEATURES.multiChildCapture && (
            <p className="mt-3 text-xs leading-6 text-ink-muted">
              可以选多个。第一个选中的是这条记录的主角，落款和文件名用他/她的名字。
            </p>
          )}
          {children.isError && <p className="text-sm text-red-700">幼儿信息加载失败，请刷新后重试</p>}
          <Link className="mt-3 inline-flex min-h-10 items-center text-sm font-medium text-brand" onClick={onClose} to={FEATURES.childMutation ? "/children" : "/settings"}>管理幼儿信息</Link>
        </StepCard>

        {submitCapture.isPending && uploadPercentage != null && (
          <div aria-label="上传进度" className="mt-4 rounded-xl bg-brand-soft px-3 py-3">
            <div className="flex justify-between text-sm font-bold text-brand-deep"><span>{uploadPercentage < 100 ? "正在上传…" : "正在保存记录…"}</span><span>{uploadPercentage}%</span></div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-white"><div className="h-full bg-brand" style={{ width: `${uploadPercentage}%` }} /></div>
          </div>
        )}
        {submitError && <p className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{submitError}</p>}

        <div className="mt-5 grid grid-cols-[1fr_2fr] gap-3">
          <button className="min-h-14 rounded-2xl bg-[#f0efeb] font-bold text-ink-muted" disabled={submitCapture.isPending} onClick={onClose} type="button">取消</button>
          <button className="flex min-h-14 items-center justify-center gap-2 rounded-2xl bg-brand font-bold text-white disabled:bg-stone-300 disabled:text-stone-500" disabled={!canSubmit} onClick={submit} type="button">{submitCapture.isPending && <LoaderCircle className="animate-spin" size={19} />}{submitCapture.isPending ? "正在上传…" : "确认"}</button>
        </div>
      </section>
    </div>
  );
}

function StepCard({ children, number, title }: { children: ReactNode; number: string; title: string }) {
  return <section className="mt-4 rounded-2xl border border-[#dfdcd4] p-4"><h3 className="mb-4 flex items-center gap-2 text-sm text-ink-muted"><span className="grid size-7 place-items-center rounded-full bg-[#e7f3ed] font-bold text-brand">{number}</span>{title}</h3>{children}</section>;
}

function FileChoice({ accept, active, icon, label, onChange }: { accept: string; active: boolean; icon: ReactNode; label: string; onChange: (event: ChangeEvent<HTMLInputElement>) => void }) {
  return <label className={`flex min-h-24 cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border ${active ? "border-brand bg-[#eaf4ef] text-brand" : "border-dashed border-[#d9d6ce] text-ink-muted"}`}>{icon}<span className="font-bold">{label}</span><input accept={accept} className="sr-only" onChange={onChange} type="file" /></label>;
}

function validateFile(file: File) {
  const type = file.type.split(";", 1)[0].trim().toLowerCase();
  const suffix = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!SUPPORTED_TYPES.has(type) && !(type === "" || type === "application/octet-stream") && !SUPPORTED_SUFFIXES.has(suffix)) return "只支持照片和视频（JPG、PNG、HEIC、MP4、MOV）";
  if (!SUPPORTED_TYPES.has(type) && !SUPPORTED_SUFFIXES.has(suffix)) return "只支持照片和视频（JPG、PNG、HEIC、MP4、MOV）";
  if (file.size > MAX_UPLOAD_SIZE_BYTES) return "文件太大了，最多 200MB。可以拍短一点的视频";
  return "";
}

function isVideo(file: File) {
  return file.type.startsWith("video/") || /\.(mp4|mov)$/i.test(file.name);
}
