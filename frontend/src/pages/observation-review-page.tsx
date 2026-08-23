import { ArrowLeft, LoaderCircle, RotateCcw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";

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

  useEffect(() => {
    if (!record || record.status !== "ready_for_review") return;
    const key = `${record.id}:${record.ready_at ?? "ready"}`;
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
      navigate("/", { replace: true });
    } catch {
      // 对应错误由页面状态展示，保留全部输入供教师直接重试。
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

  return (
    <MobilePage>
      <div className="px-5 pb-28 pt-5">
        <header className="mb-5 flex items-center gap-3">
          <Link
            aria-label="返回今日素材"
            className="grid size-11 shrink-0 place-items-center rounded-full bg-surface text-ink shadow-sm"
            onClick={flushFields}
            to="/"
          >
            <ArrowLeft size={22} />
          </Link>
          <h1 className="text-2xl font-bold tracking-[-0.02em]">整理这条记录</h1>
        </header>

        <section className="mb-6 overflow-hidden rounded-3xl bg-surface shadow-sm">
          <MediaThumbnail
            className="aspect-[16/9] w-full"
            media={media}
            mediaType={record.media_type}
          />
          <div className="px-4 py-4">
            <p className="font-bold">{record.area_name ?? "未知区域"}</p>
            <p className="mt-1 text-sm text-ink-muted">
              {formatKindergartenTime(record.created_at ?? record.observed_at)}
            </p>
          </div>
        </section>

        {record.status === "ready_for_review" && (
          <section className="mb-7 rounded-3xl bg-surface p-5 shadow-sm" aria-labelledby="child-heading">
            <h2 className="text-lg font-bold" id="child-heading">这条记录是关于谁的</h2>
            <p className="mt-1 text-sm text-ink-muted">只显示{record.classroom_name ?? "当前班级"}的幼儿，单选</p>
            {children.isLoading && <p className="mt-4 text-sm text-ink-muted">正在加载幼儿名单…</p>}
            {children.isError && <p className="mt-4 text-sm text-red-700">幼儿名单暂时没有加载成功</p>}
            <div className="mt-4 flex gap-2 overflow-x-auto pb-1" role="radiogroup" aria-label="选择幼儿">
              {classroomChildren.map((child) => (
                <button
                  aria-checked={record.child_id === child.id}
                  className={`min-h-11 shrink-0 rounded-full border px-4 text-sm font-bold ${record.child_id === child.id ? "border-brand bg-brand text-white" : "border-stone-300 bg-white text-stone-700"}`}
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
          <section className="rounded-3xl bg-surface p-5 shadow-sm">
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
          <section className="flex min-h-64 flex-col items-center justify-center rounded-3xl bg-surface px-6 text-center shadow-sm">
            <LoaderCircle aria-hidden className="animate-spin text-brand" size={36} />
            <h2 className="mt-5 text-xl font-bold">正在整理…</h2>
            <p className="mt-2 text-sm leading-6 text-ink-muted">可以先返回首页，稍后再点进来看。</p>
            <Link className="mt-6 flex min-h-11 items-center px-5 font-bold text-brand" to="/">返回今日素材</Link>
          </section>
        )}

        {record.status === "ready_for_review" && !showIndicators && (
          <section>
            <label className="block text-sm font-bold text-ink-muted" htmlFor="narrative">
              AI 生成的客观白描，请核对后修改
            </label>
            <textarea
              className="mt-3 min-h-72 w-full resize-y rounded-3xl border border-stone-200 bg-surface p-4 text-base leading-7 outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
              id="narrative"
              onBlur={flushFields}
              onChange={(event) => changeField("narrative", event.target.value)}
              value={fields.narrative}
            />
            <div className="mt-2 min-h-5 text-xs text-ink-muted" role="status">
              {updateObservation.isPending && "正在自动保存…"}
              {updateObservation.isSuccess && !updateObservation.isPending && "已自动保存"}
              {updateObservation.isError && "暂时没有保存成功，继续修改或离开输入框会重试"}
            </div>
            {isMock && (
              <p className="mt-3 text-xs leading-5 text-stone-500">⚠️ 当前为演示数据，尚未接入真实 AI</p>
            )}
          </section>
        )}

        {record.status === "ready_for_review" && showIndicators && (
          <div className="space-y-8">
            <section aria-labelledby="purpose-heading">
              <label className="block text-base font-bold" htmlFor="purpose" id="purpose-heading">观察目的</label>
              <p className="mt-1 text-sm text-ink-muted">由你填写，AI 不生成</p>
              <textarea
                className="mt-3 min-h-28 w-full resize-y rounded-3xl border border-stone-200 bg-surface p-4 text-base leading-7 outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                id="purpose"
                onBlur={flushFields}
                onChange={(event) => changeField("purpose", event.target.value)}
                placeholder="这次观察想了解什么？"
                value={fields.purpose}
              />
            </section>

            <section aria-labelledby="narrative-heading">
              <label className="block text-base font-bold" htmlFor="narrative" id="narrative-heading">客观白描</label>
              <p className="mt-1 text-sm text-ink-muted">AI 主笔，请核对事实后修改</p>
              <textarea
                className="mt-3 min-h-56 w-full resize-y rounded-3xl border border-stone-200 bg-surface p-4 text-base leading-7 outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                id="narrative"
                onBlur={flushFields}
                onChange={(event) => changeField("narrative", event.target.value)}
                value={fields.narrative}
              />
              {isMock && <p className="mt-2 text-xs text-stone-500">⚠️ 当前为演示数据，尚未接入真实 AI</p>}
            </section>

            <CandidateIndicators
              addingTeacherTag={addTeacherTag.isPending}
              indicatorOptions={indicators.data ?? []}
              onAddTeacherTag={async (indicatorCode, level) => {
                await addTeacherTag.mutateAsync({ indicatorCode, level });
              }}
              onDecide={(tagId, accepted) => decideTag.mutate({ tagId, accepted })}
              tags={record.tags}
            />

            <section aria-labelledby="analysis-heading">
              <label className="block text-base font-bold" htmlFor="analysis" id="analysis-heading">分析</label>
              <p className="mt-1 text-sm text-ink-muted">由你判断和书写，AI 不代写</p>
              {acceptedTags.length > 0 && (
                <div className="mt-3 rounded-2xl bg-stone-100 p-3">
                  <p className="text-xs font-bold text-stone-500">已采纳指标，仅供参考</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {acceptedTags.map((tag) => (
                      <span className="rounded-full bg-white px-3 py-1.5 text-xs font-bold text-stone-700" key={tag.id}>
                        {tag.indicator_code} {tag.indicator_name} · {tag.level === 1 ? "初阶" : tag.level === 2 ? "中阶" : "高阶"}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <textarea
                className="mt-3 min-h-40 w-full resize-y rounded-3xl border border-stone-200 bg-surface p-4 text-base leading-7 outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                id="analysis"
                onBlur={flushFields}
                onChange={(event) => changeField("analysis", event.target.value)}
                placeholder="结合观察到的行为，写下你的专业判断"
                ref={analysisRef}
                value={fields.analysis}
              />
            </section>

            <section aria-labelledby="strategy-heading">
              <label className="block text-base font-bold" htmlFor="strategy" id="strategy-heading">措施</label>
              <p className="mt-1 text-sm text-ink-muted">完全由你填写，保留教师最重要的专业判断</p>
              <textarea
                className="mt-3 min-h-40 w-full resize-y rounded-3xl border border-stone-200 bg-surface p-4 text-base leading-7 outline-none focus:border-brand focus:ring-2 focus:ring-brand/15"
                id="strategy"
                onBlur={flushFields}
                onChange={(event) => changeField("strategy", event.target.value)}
                placeholder="下一步准备提供什么材料、提问或支持？"
                ref={strategyRef}
                value={fields.strategy}
              />
            </section>

            <div className="min-h-5 text-xs text-ink-muted" role="status">
              {updateObservation.isPending && "正在保存修改…"}
              {updateObservation.isSuccess && !updateObservation.isPending && "修改已保存"}
              {updateObservation.isError && "修改暂时没有保存成功，请继续编辑后重试"}
            </div>
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

        {record.status === "confirmed" && (
          <section className="rounded-3xl bg-surface p-5 text-center shadow-sm">
            <p className="font-bold">这条记录已经完成</p>
            <Link className="mt-4 inline-flex min-h-11 items-center px-5 font-bold text-brand" to={`/observations/${id}`}>查看详情</Link>
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
        <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200/70 bg-canvas/95 px-5 pt-3">
          <button
            className="min-h-14 w-full rounded-2xl bg-brand text-lg font-bold text-white disabled:bg-stone-200 disabled:text-stone-400"
            disabled={!fields.narrative.trim() || updateObservation.isPending || suggestTags.isPending}
            onClick={() => void continueToIndicators()}
            type="button"
          >
            {suggestTags.isPending ? "正在生成候选…" : "下一步"}
          </button>
        </div>
      )}

      {record.status === "ready_for_review" && showIndicators && (
        <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200/70 bg-canvas/95 px-5 pt-3">
          {record.child_id == null && (
            <p className="mb-2 text-center text-sm font-medium text-amber-700">请先选择这条记录关于哪位幼儿</p>
          )}
          <button
            className="min-h-14 w-full rounded-2xl bg-brand text-lg font-bold text-white disabled:bg-stone-200 disabled:text-stone-400"
            disabled={record.child_id == null || confirmation.isPending}
            onClick={requestConfirmation}
            type="button"
          >
            {confirmation.isPending ? "正在确认…" : "确认完成"}
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
