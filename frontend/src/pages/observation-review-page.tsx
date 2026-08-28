import { ArrowLeft, LoaderCircle, Play, RotateCcw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { CandidateIndicators } from "../components/candidate-indicators";
import { MediaThumbnail } from "../components/media-thumbnail";
import { MobilePage } from "../components/mobile-page";
import {
  useAddTeacherTag,
  useChildren,
  useConfirmObservation,
  useGenerateNarrative,
  useDecideTag,
  useIndicators,
  useObservation,
  useSuggestTags,
  useUpdateObservation,
  getMediaFileUrl,
} from "../features/observations/api";
import { formatKindergartenTime } from "../lib/date-time";

function humanizeFailure(reason?: string | null) {
  if (!reason) return "这次没有整理成功，请重新试一次";
  if (/素材|绑定/.test(reason)) return "素材还没有准备好，请返回首页确认后再试";
  if (/网络|timeout|timed out|connection/i.test(reason)) return "网络不太稳定，这次没有整理完成，请重新试一次";
  return "这次没有整理成功，请重新试一次";
}

interface EditableFields {
  purpose: string;
  narrative: string;
  analysis: string;
  strategy: string;
}

const EMPTY_FIELDS: EditableFields = {
  purpose: "",
  narrative: "",
  analysis: "",
  strategy: "",
};

function formatDuration(duration?: number | null) {
  if (!duration) return null;
  const minutes = Math.floor(duration / 60);
  const seconds = String(duration % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export function ObservationReviewPage() {
  const { observationId } = useParams();
  const id = Number(observationId);
  const navigate = useNavigate();
  const observation = useObservation(id);
  const children = useChildren();
  const indicators = useIndicators();
  const generation = useGenerateNarrative(id);
  const updateObservation = useUpdateObservation(id);
  const suggestTags = useSuggestTags(id);
  const decideTag = useDecideTag(id);
  const addTeacherTag = useAddTeacherTag(id);
  const confirmation = useConfirmObservation(id);
  const [fields, setFields] = useState<EditableFields>(EMPTY_FIELDS);
  const fieldsRef = useRef(fields);
  const [showConfirmPrompt, setShowConfirmPrompt] = useState(false);
  const [editingPurpose, setEditingPurpose] = useState(false);
  const [editingNarrative, setEditingNarrative] = useState(false);
  const initializedKey = useRef("");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const analysisRef = useRef<HTMLTextAreaElement | null>(null);
  const strategyRef = useRef<HTMLTextAreaElement | null>(null);
  const record = observation.data;
  const candidateTags = record?.tags.filter((tag) => (
    tag.source === "system_determined" || tag.source === "ai_suggested"
  )) ?? [];
  const showIndicators = candidateTags.length > 0 || suggestTags.isSuccess;
  const classroomChildren = useMemo(() => (
    (children.data ?? []).filter((child) => child.classroom_id === record?.classroom_id)
  ), [children.data, record?.classroom_id]);
  const acceptedTags = record?.tags.filter((tag) => tag.accepted === true) ?? [];
  const selectedChild = classroomChildren.find((child) => child.id === record?.child_id);

  useEffect(() => {
    if (!record || !["ready_for_review", "confirmed"].includes(record.status)) return;
    const key = `${record.id}:${record.ready_at ?? "ready"}:${record.confirmed_at ?? "draft"}`;
    if (initializedKey.current !== key) {
      initializedKey.current = key;
      const initialFields = {
        purpose: record.purpose ?? "",
        narrative: record.narrative ?? "",
        analysis: record.analysis ?? "",
        strategy: record.strategy ?? "",
      };
      fieldsRef.current = initialFields;
      setFields(initialFields);
    }
  }, [record]);

  const isMock = generation.data?.is_mock === true
    || (Number.isInteger(id) && sessionStorage.getItem(`narrative-is-mock:${id}`) === "true");

  function save(nextFields = fieldsRef.current) {
    if (!record) return;
    const changed = Object.entries(nextFields).some(([key, value]) => (
      value !== (record[key as keyof EditableFields] ?? "")
    ));
    if (changed) updateObservation.mutate(nextFields);
  }

  function changeField(field: keyof EditableFields, value: string) {
    const nextFields = { ...fieldsRef.current, [field]: value };
    fieldsRef.current = nextFields;
    setFields(nextFields);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => save(nextFields), 700);
  }

  function flushFields() {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = null;
    save();
  }

  async function continueToIndicators() {
    if (!record) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = null;
    try {
      if (fields.narrative !== (record.narrative ?? "")) {
        await updateObservation.mutateAsync({ narrative: fields.narrative });
      }
      suggestTags.mutate();
    } catch {
      // 保存错误已由页面状态提示；白描未落库时不能基于旧内容生成候选。
    }
  }

  async function confirmNow() {
    if (!record?.child_id) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = null;
    try {
      await updateObservation.mutateAsync(fieldsRef.current);
      await confirmation.mutateAsync();
      navigate(`/observations/${id}`, { replace: true });
    } catch {
      // 对应错误由页面状态展示，保留全部输入供教师直接重试。
    }
  }

  async function saveAndReturnToDetail() {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = null;
    try {
      await updateObservation.mutateAsync(fieldsRef.current);
      navigate(`/observations/${id}`);
    } catch {
      // 保留当前输入和页面，让教师直接重试。
    }
  }

  function requestConfirmation() {
    if (!record?.child_id) return;
    if (!fields.analysis.trim() || !fields.strategy.trim()) {
      setShowConfirmPrompt(true);
      return;
    }
    void confirmNow();
  }

  function continueWriting() {
    setShowConfirmPrompt(false);
    const target = !fields.analysis.trim() ? analysisRef.current : strategyRef.current;
    target?.focus();
    target?.scrollIntoView({ block: "center" });
  }

  if (!Number.isInteger(id) || id <= 0) {
    return <ReviewMessage title="找不到这条记录" />;
  }

  if (observation.isLoading) {
    return <ReviewMessage loading title="正在打开这条记录…" />;
  }

  if (observation.isError || !record) {
    return (
      <ReviewMessage title="这条记录暂时打不开">
        <button
          className="mt-6 flex min-h-12 items-center justify-center gap-2 rounded-2xl bg-brand px-5 font-bold text-white"
          onClick={() => void observation.refetch()}
          type="button"
        >
          <RotateCcw size={18} /> 重新加载
        </button>
      </ReviewMessage>
    );
  }

  const media = record.media[0];
  const isConfirmedEditing = record.status === "confirmed";
  const childLabel = selectedChild?.name ?? record.child_name ?? "未选择幼儿";
  const durationLabel = formatDuration(media?.duration_sec);
  const materialType = record.media_type === "video" ? "视频素材" : "照片素材";
  const autosaveText = updateObservation.isPending
    ? "保存中…"
    : updateObservation.isError
      ? "保存失败"
      : "已自动保存";

  return (
    <MobilePage>
      <div className="px-4 pb-36 pt-4 sm:px-5">
        <header className="mb-4 grid grid-cols-[44px_1fr_76px] items-center">
          <Link
            aria-label={isConfirmedEditing ? "返回观察记录详情" : "返回今日素材"}
            className="grid size-11 place-items-center text-ink-muted"
            onClick={(event) => {
              if (isConfirmedEditing) {
                event.preventDefault();
                void saveAndReturnToDetail();
              } else {
                flushFields();
              }
            }}
            to={isConfirmedEditing ? `/observations/${id}` : "/"}
          >
            <ArrowLeft size={20} />
          </Link>
          <h1 className="text-center text-xl font-bold tracking-[-0.02em]">
            {isConfirmedEditing ? "观察记录 · 继续编辑" : "草稿 · 观察记录"}
          </h1>
          <p className={`text-right text-xs ${updateObservation.isError ? "text-red-700" : "text-ink-muted"}`} role="status">
            {autosaveText}
          </p>
        </header>

        <section className="mb-5 flex items-center gap-3 rounded-2xl border border-stone-200 bg-white p-3.5 shadow-sm">
          <a className="relative block size-[76px] shrink-0 overflow-hidden rounded-xl" href={media ? getMediaFileUrl(media.id) : undefined} target="_blank">
            <MediaThumbnail className="size-full" media={media} mediaType={record.media_type} />
            {record.media_type === "video" && (
              <span className="absolute inset-0 grid place-items-center bg-black/10 text-white"><Play fill="currentColor" size={23} /></span>
            )}
            {durationLabel && <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">{durationLabel}</span>}
          </a>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[15px] font-bold">{record.area_name ?? "观察素材"} · {materialType}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="rounded-full bg-brand-soft px-2.5 py-1 text-xs font-bold text-brand-deep">{childLabel}</span>
              <span className="rounded-full bg-stone-100 px-2.5 py-1 text-xs text-ink-muted">{record.area_name ?? "未知区域"}</span>
              <span className="rounded-full bg-stone-100 px-2.5 py-1 text-xs text-ink-muted">{formatKindergartenTime(record.created_at ?? record.observed_at)}</span>
            </div>
            <p className="mt-2 text-xs font-medium text-brand">● 素材已保存 · 可回看原素材</p>
          </div>
        </section>

        {record.status === "ready_for_review" && (
          <section className="mb-5" aria-labelledby="child-heading">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-bold" id="child-heading">观察对象</h2>
              <p className="text-xs text-ink-muted">{record.classroom_name ?? "当前班级"} · 单选</p>
            </div>
            {children.isLoading && <p className="text-sm text-ink-muted">正在加载幼儿信息…</p>}
            {children.isError && <p className="text-sm text-red-700">幼儿信息加载失败</p>}
            <div className="flex gap-2 overflow-x-auto pb-1" role="radiogroup" aria-label="选择幼儿">
              {classroomChildren.map((child) => (
                <button
                  aria-checked={record.child_id === child.id}
                  className={`min-h-10 shrink-0 rounded-full border px-4 text-sm font-bold ${record.child_id === child.id ? "border-brand bg-brand text-white" : "border-stone-300 bg-white text-stone-700"}`}
                  disabled={updateObservation.isPending && updateObservation.variables?.child_id === child.id}
                  key={child.id}
                  onClick={() => updateObservation.mutate({ child_id: child.id })}
                  role="radio"
                  type="button"
                >
                  {child.name}
                </button>
              ))}
            </div>
          </section>
        )}

        {record.status === "uploaded" && (
          <section className="rounded-2xl bg-white p-5 shadow-sm">
            <h2 className="text-lg font-bold">素材已经存好了</h2>
            <p className="mt-2 text-sm leading-6 text-ink-muted">让 AI 先把画面里的行为整理成客观白描。</p>
            <button
              className="mt-6 flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-brand text-lg font-bold text-white disabled:opacity-60"
              disabled={generation.isPending}
              onClick={() => generation.mutate()}
              type="button"
            >
              <Sparkles size={20} /> 让 AI 先整理一遍
            </button>
          </section>
        )}

        {record.status === "processing" && (
          <section className="flex min-h-64 flex-col items-center justify-center rounded-2xl bg-white px-6 text-center shadow-sm">
            <LoaderCircle aria-hidden className="animate-spin text-brand" size={36} />
            <h2 className="mt-5 text-xl font-bold">正在整理…</h2>
            <p className="mt-2 text-sm leading-6 text-ink-muted">可以先返回首页，稍后再点进来看。</p>
            <Link className="mt-6 flex min-h-11 items-center px-5 font-bold text-brand" to="/">返回今日素材</Link>
          </section>
        )}

        {["ready_for_review", "confirmed"].includes(record.status) && (
          <div>
            <SectionHeading hint="教师填写" title="观察目的" />
            <section className="rounded-2xl border border-stone-200 bg-white p-4">
              {editingPurpose ? (
                <>
                  <textarea
                    autoFocus
                    className="min-h-24 w-full resize-y rounded-xl border border-brand/30 bg-stone-50 p-3 text-sm leading-6 outline-none focus:border-brand"
                    id="purpose"
                    onBlur={flushFields}
                    onChange={(event) => changeField("purpose", event.target.value)}
                    placeholder="这次观察想了解什么？"
                    value={fields.purpose}
                  />
                  <div className="mt-3 flex justify-end">
                    <button className="min-h-9 rounded-full bg-brand px-4 text-xs font-bold text-white" onClick={() => { flushFields(); setEditingPurpose(false); }} type="button">完成</button>
                  </div>
                </>
              ) : (
                <div className="flex items-start justify-between gap-3">
                  <p className={`text-sm leading-7 ${fields.purpose ? "text-ink" : "text-stone-400"}`}>{fields.purpose || "还没有填写观察目的"}</p>
                  <button className="min-h-9 shrink-0 rounded-full border border-dashed border-brand/30 px-3 text-xs font-bold text-brand" onClick={() => setEditingPurpose(true)} type="button">+ 修改</button>
                </div>
              )}
            </section>

            <SectionHeading hint="AI 草拟 · 可直接改" title="白描记录" />
            <section className="rounded-2xl border border-stone-200 bg-white p-4">
              {editingNarrative ? (
                <textarea
                  autoFocus
                  className="min-h-56 w-full resize-y rounded-xl border border-brand/30 bg-stone-50 p-3 text-sm leading-7 outline-none focus:border-brand"
                  id="narrative"
                  onBlur={flushFields}
                  onChange={(event) => changeField("narrative", event.target.value)}
                  value={fields.narrative}
                />
              ) : (
                <p className="whitespace-pre-wrap text-[15px] leading-8">{fields.narrative}</p>
              )}
              <div className="mt-3 flex items-center justify-between gap-3 border-t border-dashed border-stone-200 pt-3">
                <span className="text-xs text-ink-muted">{record.narrative_source === "ai_edited" ? "你已改写这一段" : "请结合原素材核对事实"}</span>
                <button
                  className={`min-h-9 shrink-0 rounded-full border px-3 text-xs font-bold ${editingNarrative ? "border-brand bg-brand text-white" : "border-brand/30 text-brand"}`}
                  onClick={() => { if (editingNarrative) flushFields(); setEditingNarrative((value) => !value); }}
                  type="button"
                >
                  {editingNarrative ? "改好了" : "这段不像我看到的"}
                </button>
              </div>
              {isMock && <MockNarrativeNotice className="mt-2 text-xs text-stone-500" />}
            </section>

            {showIndicators && (
              <>
                <SectionHeading hint="逐条判断" title="指标推荐" />
                <CandidateIndicators
                  addingTeacherTag={addTeacherTag.isPending}
                  indicatorOptions={indicators.data ?? []}
                  onAddTeacherTag={async (indicatorCode, level) => {
                    await addTeacherTag.mutateAsync({ indicatorCode, level });
                  }}
                  onDecide={(tagId, accepted) => decideTag.mutate({ tagId, accepted })}
                  tags={record.tags}
                />

                <SectionHeading hint="写给家长看的判断" title="我的分析" />
                <section className="rounded-2xl border border-stone-200 bg-white p-4">
                  {acceptedTags.length > 0 && (
                    <div className="mb-3 flex flex-wrap gap-1.5">
                      {acceptedTags.map((tag) => (
                        <span className="rounded-full bg-brand-soft px-2.5 py-1 text-[11px] font-bold text-brand-deep" key={tag.id}>{tag.indicator_name}</span>
                      ))}
                    </div>
                  )}
                  <textarea
                    className="min-h-28 w-full resize-y rounded-xl border border-stone-200 bg-stone-50 p-3 text-sm leading-7 outline-none focus:border-brand"
                    id="analysis"
                    onBlur={flushFields}
                    onChange={(event) => changeField("analysis", event.target.value)}
                    placeholder="结合观察到的行为，写下你的专业判断（选填）"
                    ref={analysisRef}
                    value={fields.analysis}
                  />
                </section>

                <SectionHeading hint="你来写" title="下一步支持策略" />
                <section className="rounded-2xl border border-stone-200 bg-white p-4">
                  <textarea
                    className="min-h-28 w-full resize-y rounded-xl border border-stone-200 bg-stone-50 p-3 text-sm leading-7 outline-none focus:border-brand"
                    id="strategy"
                    onBlur={flushFields}
                    onChange={(event) => changeField("strategy", event.target.value)}
                    placeholder="下一步准备提供什么材料、提问或支持？"
                    ref={strategyRef}
                    value={fields.strategy}
                  />
                </section>
              </>
            )}
          </div>
        )}

        {record.status === "failed" && (
          <section className="rounded-3xl border border-red-100 bg-red-50 p-5">
            <h2 className="text-lg font-bold text-red-800">整理没有完成</h2>
            <p className="mt-2 text-sm leading-6 text-red-700">{humanizeFailure(record.failure_reason)}</p>
            <button
              className="mt-6 flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-red-700 text-lg font-bold text-white disabled:opacity-60"
              disabled={generation.isPending}
              onClick={() => generation.mutate()}
              type="button"
            >
              <RotateCcw size={19} /> 重新整理
            </button>
          </section>
        )}

        {generation.isError && record.status !== "failed" && (
          <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">这次没有整理成功，请重新试一次</p>
        )}
        {suggestTags.isError && (
          <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">候选指标暂时没有生成成功，请点“下一步”重试</p>
        )}
        {decideTag.isError && (
          <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">这次选择没有保存成功，请再点一次</p>
        )}
        {addTeacherTag.isError && (
          <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">补充指标暂时没有保存成功，请直接重试</p>
        )}
        {confirmation.isError && (
          <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">这条记录暂时没有确认成功，内容都还在，请重试</p>
        )}
      </div>

      {record.status === "ready_for_review" && !showIndicators && (
        <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200 bg-canvas/95 px-4 pt-3 backdrop-blur">
          <button
            className="min-h-14 w-full rounded-2xl bg-brand text-base font-bold text-white disabled:bg-stone-200 disabled:text-stone-400"
            disabled={!fields.narrative.trim() || updateObservation.isPending || suggestTags.isPending}
            onClick={() => void continueToIndicators()}
            type="button"
          >
            {suggestTags.isPending ? "正在生成候选…" : "生成候选指标"}
          </button>
          <p className="mt-2 text-center text-xs text-ink-muted">白描会先自动保存，再用于生成候选</p>
        </div>
      )}

      {record.status === "ready_for_review" && showIndicators && (
        <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200 bg-canvas/95 px-4 pt-3 backdrop-blur">
          {record.child_id == null && (
            <p className="mb-2 text-center text-sm font-medium text-amber-700">请先选择这条记录关于哪位幼儿</p>
          )}
          {record.child_id != null && acceptedTags.length === 0 && (
            <p className="mb-2 text-center text-sm font-medium text-amber-700">请至少采纳一个指标</p>
          )}
          <button
            className="min-h-14 w-full rounded-2xl bg-brand text-base font-bold text-white disabled:bg-stone-200 disabled:text-stone-400"
            disabled={record.child_id == null || acceptedTags.length === 0 || confirmation.isPending}
            onClick={requestConfirmation}
            type="button"
          >
            {confirmation.isPending ? "正在生成完整稿…" : "保存并生成完整稿"}
          </button>
          <p className="mt-2 text-center text-xs text-ink-muted">生成后进入完整记录，仍可继续修改</p>
        </div>
      )}

      {record.status === "confirmed" && showIndicators && (
        <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200 bg-canvas/95 px-4 pt-3 backdrop-blur">
          <button
            className="min-h-14 w-full rounded-2xl bg-brand text-base font-bold text-white disabled:bg-stone-200 disabled:text-stone-400"
            onClick={() => void saveAndReturnToDetail()}
            type="button"
          >
            保存并返回完整稿
          </button>
        </div>
      )}

      {showConfirmPrompt && (
        <div className="fixed inset-0 z-30 flex items-end justify-center bg-black/35 p-4 sm:items-center" role="presentation">
          <section aria-labelledby="confirm-prompt-heading" aria-modal="true" className="w-full max-w-sm rounded-3xl bg-white p-5 shadow-xl" role="dialog">
            <h2 className="text-xl font-bold" id="confirm-prompt-heading">分析和措施还没写</h2>
            <p className="mt-3 text-sm leading-6 text-ink-muted">现在确认的话可以之后再补。要现在写吗？</p>
            <div className="mt-6 grid grid-cols-2 gap-3">
              <button
                className="min-h-12 rounded-xl border border-brand font-bold text-brand"
                disabled={confirmation.isPending}
                onClick={() => void confirmNow()}
                type="button"
              >
                先确认
              </button>
              <button className="min-h-12 rounded-xl bg-brand font-bold text-white" onClick={continueWriting} type="button">
                继续写
              </button>
            </div>
          </section>
        </div>
      )}
    </MobilePage>
  );
}

function SectionHeading({ hint, title }: { hint: string; title: string }) {
  return (
    <div className="mb-2 mt-6 flex items-center gap-2 px-0.5">
      <span aria-hidden className="h-4 w-1 rounded-full bg-brand" />
      <h2 className="text-lg font-bold">{title}</h2>
      <span className="ml-auto text-xs text-ink-muted">{hint}</span>
    </div>
  );
}

export function MockNarrativeNotice({ className }: { className: string }) {
  const [searchParams] = useSearchParams();
  if (searchParams.get("demo") === "1") return null;
  return <p className={className}>⚠️ 当前为演示数据，尚未接入真实 AI</p>;
}

function ReviewMessage({ children, loading = false, title }: { children?: ReactNode; loading?: boolean; title: string }) {
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
