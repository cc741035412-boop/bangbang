import { ArrowLeft, LoaderCircle, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { CandidateIndicators } from "../components/candidate-indicators";
import { ChildNameInserter } from "../components/child-name-inserter";
import { AreaBadge } from "../components/area-badge";
import { MediaThumbnail } from "../components/media-thumbnail";
import { MobilePage } from "../components/mobile-page";
import {
  useAddTeacherTag,
  useObservationPeople,
  useAssignObservationPeople,
  useChildren,
  useConfirmObservation,
  useGenerateNarrative,
  useDecideTag,
  useDeleteObservation,
  useIndicators,
  useObservation,
  useReplaceObservationChildren,
  useSuggestAnalysis,
  useSuggestTags,
  useUpdateObservation,
  getMediaFileUrl,
  getMediaThumbnailUrl,
} from "../features/observations/api";
import { ObservationGoals } from "../features/observations/observation-goals";
import { formatKindergartenTime } from "../lib/date-time";
import { childAccent } from "../lib/child-colors";

interface EditableFields {
  purpose: string;
  note: string;
  narrative: string;
  analysis: string;
  strategy: string;
}

const EMPTY_FIELDS: EditableFields = {
  purpose: "",
  note: "",
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
  const [searchParams] = useSearchParams();
  const id = Number(observationId);
  const navigate = useNavigate();
  const observation = useObservation(id);
  const children = useChildren();
  const indicators = useIndicators();
  const generation = useGenerateNarrative(id);
  const updateObservation = useUpdateObservation(id);
  const suggestTags = useSuggestTags(id);
  const suggestAnalysis = useSuggestAnalysis(id);
  const decideTag = useDecideTag(id);
  const addTeacherTag = useAddTeacherTag(id);
  const confirmation = useConfirmObservation(id);
  const deleteObservation = useDeleteObservation(id);
  const replaceChildren = useReplaceObservationChildren(id);
  const [fields, setFields] = useState<EditableFields>(EMPTY_FIELDS);
  const fieldsRef = useRef(fields);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [reviewingFacts, setReviewingFacts] = useState(searchParams.get("step") !== "writing");
  const [writing, setWriting] = useState(searchParams.get("step") === "writing");
  const [identitySaved, setIdentitySaved] = useState(false);
  const [actionError, setActionError] = useState("");
  const [starting, setStarting] = useState(false);
  const saveQueue = useRef<Promise<unknown>>(Promise.resolve());
  const [editingNarrative, setEditingNarrative] = useState(false);
  const initializedKey = useRef("");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (saveTimer.current) clearTimeout(saveTimer.current); }, []);
  const record = observation.data;
  const currentChildIds = replaceChildren.selectedIds ?? (record?.children?.length ? record.children.map((child) => child.id) : record?.child_id ? [record.child_id] : []);
  const currentPrimaryId = currentChildIds[0] ?? null;
  const people = useObservationPeople(id, record?.narrative ?? "", Boolean(record?.narrative && fields.narrative === record.narrative && !editingNarrative && reviewingFacts && !record.narrative_context_changed));
  const assignPeople = useAssignObservationPeople(id);
  const candidateTags = record?.tags.filter((tag) => (
    tag.source === "system_determined" || tag.source === "ai_suggested"
  )) ?? [];
  const showIndicators = !record?.suggestions_stale && (record?.status === "confirmed" || record?.suggestions_ready || candidateTags.length > 0 || suggestTags.isSuccess);
  const inJudgment = Boolean(showIndicators && !reviewingFacts);
  const classroomChildren = (children.data ?? []).filter((child) => (
    // 记录还没有归属班级时显示全部幼儿，避免"选不了幼儿导致卡住"。
    record?.classroom_id == null || child.classroom_id === record.classroom_id
  ));
  const acceptedTags = record?.tags.filter((tag) => tag.accepted === true) ?? [];
  const analysisContext = `${record?.narrative ?? ""}:${record?.purpose ?? ""}:${acceptedTags.map((tag) => tag.id).join(",")}`;
  const resetAnalysis = suggestAnalysis.reset;
  useEffect(() => { resetAnalysis(); }, [analysisContext, resetAnalysis]);
  const selectedChild = classroomChildren.find((child) => child.id === currentPrimaryId);
  const purposePresets = useMemo(
    () => buildPurposePresets(),
    [],
  );

  useEffect(() => {
    if (!record) return;
    const key = `${record.id}:${record.narrative_ai_raw ?? ""}`;
    if (initializedKey.current !== key) {
      initializedKey.current = key;
      const initialFields = {
        purpose: record.purpose ?? "",
        note: record.note ?? "",
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
    if (changed) void persistFields(nextFields).catch(() => {});
  }

  function changeField(field: keyof EditableFields, value: string) {
    if (assignPeople.isPending) return;
    const nextFields = { ...fieldsRef.current, [field]: value };
    fieldsRef.current = nextFields;
    setFields(nextFields);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => save(nextFields), 700);
  }

  function persistFields(nextFields = fieldsRef.current) {
    const operation = saveQueue.current.catch(() => {}).then(() => updateObservation.mutateAsync(nextFields));
    saveQueue.current = operation;
    return operation;
  }

  async function startNarrative(mode: "focused" | "explore") {
    if (starting || generation.isPending) return;
    if (mode === "focused" && !fieldsRef.current.purpose.trim()) { setActionError("请选择或添加至少一个观察目标"); return; }
    if (saveTimer.current) clearTimeout(saveTimer.current);
    setStarting(true);
    setActionError("");
    try {
      await replaceChildren.flush();
      await persistFields();
      await generation.mutateAsync(mode);
      setReviewingFacts(true);
      window.scrollTo(0, 0);
    } catch {
      setActionError("没有完成，请检查保存状态后重试，素材仍在。");
    } finally { setStarting(false); }
  }

  function flushFields() {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = null;
    save();
  }

  async function continueToIndicators() {
    if (!record) return;
    if (!currentPrimaryId || !fieldsRef.current.purpose.trim()) {
      setActionError("请先选择幼儿和至少一个观察目标");
      document.getElementById("goal-section")?.scrollIntoView({ block: "center" });
      return;
    }
    if (saveTimer.current) clearTimeout(saveTimer.current);
    setActionError("");
    try {
      await replaceChildren.flush();
      await persistFields();
      if (record.status !== "confirmed") await suggestTags.mutateAsync();
      setWriting(false);
      setReviewingFacts(false);
      window.scrollTo(0, 0);
    } catch { setActionError("没有完成推荐，请核对观察信息并重试。"); }
  }

  async function confirmNow() {
    if (!record?.child_id || !fieldsRef.current.purpose.trim() || !fieldsRef.current.analysis.trim() || !fieldsRef.current.strategy.trim()) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = null;
    try {
      await persistFields();
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
      const saved = await persistFields();
      if (saved.status === "confirmed") navigate(`/observations/${id}`);
      else setReviewingFacts(true);
    } catch {
      // 保留当前输入和页面，让教师直接重试。
    }
  }

  function requestConfirmation() {
    if (!record?.child_id) return;
    if (!fields.purpose.trim()) {
      setReviewingFacts(true);
      document.getElementById("goal-section")?.scrollIntoView({ block: "center" });
      return;
    }
    void confirmNow();
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
  const autosaveText = updateObservation.isPending || replaceChildren.isPending
    ? "保存中…"
    : updateObservation.isError || replaceChildren.isError
      ? "保存失败"
      : "已自动保存";

  return (
    <MobilePage>
      <div className="px-4 pb-36 pt-4 sm:px-5">
        <header className="mb-4 grid grid-cols-[44px_1fr_76px] items-center">
          <button
            type="button"
            aria-label="返回今日素材"
            className="grid size-11 place-items-center text-ink-muted"
            onClick={() => {
              flushFields();
              navigate("/");
            }}
          >
            <ArrowLeft size={20} />
          </button>
          <h1 className="text-center text-xl font-bold tracking-[-0.02em]">
            {isConfirmedEditing ? "观察记录 · 继续编辑" : "草稿 · 观察记录"}
          </h1>
          <p className={`text-right text-xs ${updateObservation.isError ? "text-red-700" : "text-ink-muted"}`} role="status">
            {autosaveText}
          </p>
        </header>

        <nav aria-label="报告生成进度" className="mb-4 flex items-center justify-between rounded-xl bg-white px-3 py-3 text-xs text-ink-muted">
          <span className={record.status === "uploaded" ? "font-bold text-brand" : ""}>1 准备观察</span><span>→</span>
          <span className={!inJudgment && record.status === "ready_for_review" ? "font-bold text-brand" : ""}>2 核对白描</span><span>→</span>
          <span className={inJudgment ? "font-bold text-brand" : ""}>3 判断与导出</span>
        </nav>
        {inJudgment && <button className="mb-3 min-h-11 text-base font-bold text-brand" onClick={() => setReviewingFacts(true)} type="button">← 返回核对白描与目标</button>}

        <section className="mb-5 flex items-center gap-3 rounded-2xl border border-stone-200 bg-white p-3.5 shadow-sm">
          {record.media_type === "video" && media ? (
            <video
              aria-label="视频素材预览（静音）"
              className="relative size-[76px] shrink-0 overflow-hidden rounded-xl object-cover"
              controls
              muted
              playsInline
              poster={getMediaThumbnailUrl(media.id)}
              preload="metadata"
              src={getMediaFileUrl(media.id)}
            />
          ) : (
            <div className="relative block size-[76px] shrink-0 overflow-hidden rounded-xl">
              <MediaThumbnail className="size-full" media={media} mediaType={record.media_type} />
              {durationLabel && <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">{durationLabel}</span>}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-[15px] font-bold">{record.area_name ?? "观察素材"} · {materialType}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <ChildBadge childLabel={childLabel} childId={currentPrimaryId} />
              <AreaBadge name={record.area_name ?? "未知区域"} />
              <span className="rounded-full bg-stone-100 px-2.5 py-1 text-xs text-ink-muted">{formatKindergartenTime(record.created_at ?? record.observed_at)}</span>
            </div>
            <p className="mt-2 text-xs font-medium text-brand">● 素材已保存 · 可回看原素材</p>
          </div>
        </section>

        {["uploaded", "ready_for_review", "failed"].includes(record.status) && !inJudgment && !generation.isPending && (
          <section className="mb-5" aria-labelledby="child-heading">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-bold" id="child-heading">主观察幼儿（选一位）</h2>
              <p className="text-xs text-ink-muted">{record.classroom_name ?? "当前班级"}</p>
            </div>
            {children.isLoading && <p className="text-sm text-ink-muted">正在加载幼儿信息…</p>}
            {children.isError && (
              <div className="flex items-center gap-3 text-sm text-red-700">
                <p>幼儿信息加载失败</p>
                <button className="min-h-11 font-bold underline" onClick={() => void children.refetch()} type="button">重新加载</button>
              </div>
            )}
            {!children.isLoading && !children.isError && classroomChildren.length === 0 && (
              <div className="rounded-2xl border border-stone-200 bg-white px-4 py-3 text-sm">
                <p className="text-ink-muted">当前班级还没有幼儿名单，添加后即可选择观察对象。</p>
                <Link className="mt-1 inline-flex min-h-11 items-center font-bold text-brand" onClick={flushFields} to="/children">添加幼儿</Link>
              </div>
            )}
            <p className="mb-3 text-sm leading-6 text-ink-muted">这条记录重点观察谁？点名字可直接切换。</p>
            <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="主观察幼儿">
              {classroomChildren.map((child) => {
                const primary = currentPrimaryId === child.id;
                return <button
                  role="radio"
                  aria-label={child.name}
                  aria-checked={primary}
                  className={`min-h-14 min-w-0 rounded-2xl border px-2 py-2 text-base font-bold ${primary ? "border-brand bg-brand text-white" : "border-stone-300 bg-white text-ink"}`}
                  disabled={assignPeople.isPending || starting}
                  key={child.id}
                  onClick={() => { if (!primary) replaceChildren.mutate([child.id, ...currentChildIds.filter((cid) => cid !== child.id)]); }}
                  type="button"
                >
                  <span className="block break-all">{child.name}</span>
                  {primary && <span className="block text-sm font-normal">主观察</span>}
                </button>;
              })}
            </div>
            {currentPrimaryId && <>
              <h3 className="mb-2 mt-4 text-sm font-bold">同时记录的其他幼儿（可多选）</h3>
              <div className="grid grid-cols-2 gap-2" role="group" aria-label="其他幼儿">
                {classroomChildren.filter((child) => child.id !== currentPrimaryId).map((child) => {
                  const selected = currentChildIds.includes(child.id);
                  return <button role="checkbox" aria-label={child.name} aria-checked={selected} className={`min-h-12 rounded-xl border px-2 text-base font-bold ${selected ? "border-brand bg-brand-soft text-brand-deep" : "border-stone-300 bg-white text-ink-muted"}`} disabled={assignPeople.isPending || starting} key={child.id} onClick={() => replaceChildren.mutate(selected ? currentChildIds.filter((cid) => cid !== child.id) : [...currentChildIds, child.id])} type="button">{selected ? "✓ " : ""}{child.name}</button>;
                })}
              </div>
              <p className="mt-2 text-sm leading-6 text-ink-muted">切换主体后，原主体会留在这里；不需要记录时可取消。</p>
            </>}
            <p className={`mt-3 text-sm ${replaceChildren.isError ? "text-red-700" : "text-brand"}`} role="status">
              {replaceChildren.isError ? "选择未保存，请重试后继续" : replaceChildren.isPending ? "已选好，正在保存…可继续切换" : currentPrimaryId ? `主观察：${selectedChild?.name ?? "已选择"} · 其他 ${Math.max(0, currentChildIds.length - 1)} 位` : "也可以先生成白描，再根据衣着和行为对应姓名"}
            </p>
            {replaceChildren.isError && <button className="min-h-11 text-base font-bold text-red-700 underline" onClick={replaceChildren.retry} type="button">重试保存观察对象</button>}
            <label className="mt-3 block text-sm text-ink-muted" htmlFor="subject-note">画面中是哪位幼儿？（选填）</label>
            <textarea className="mt-2 min-h-20 w-full rounded-xl border border-stone-200 bg-white p-3 text-base" disabled={starting} id="subject-note" onBlur={flushFields} onChange={(event) => changeField("note", event.target.value)} placeholder="例如：王小满是左侧红衣幼儿，李念安是右侧蓝衣幼儿" value={fields.note} />
            <p className="mt-1 text-xs leading-5 text-ink-muted">未填时 AI 使用人物代号，请在下一步核对对应关系。</p>
          </section>
        )}

        {["uploaded", "failed", "ready_for_review", "confirmed"].includes(record.status) && !inJudgment && !generation.isPending && (
          <div id="goal-section">
            <SectionHeading hint="可多选 · 可自己添加" title="观察目标" />
            <ObservationGoals disabled={starting} onChange={(value) => changeField("purpose", value)} presets={purposePresets} value={fields.purpose} />
            {record.observation_mode === "explore" && record.narrative && <p className="mt-2 text-sm leading-6 text-ink-muted">刚才是先看看素材。现在请确认想关注的目标，再推荐指标。</p>}
          </div>
        )}
        {(["uploaded", "failed"].includes(record.status) || record.narrative_context_changed) && !generation.isPending && (
          <section className="mt-4 rounded-2xl bg-white p-4">
            {record.narrative_context_changed && <p className="mb-3 text-sm leading-6 text-amber-800">观察对象或目标已改变，请重新生成并核对白描。原内容会在生成完成前保留。</p>}
            <button className="flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-brand text-base font-bold text-white disabled:opacity-50" disabled={starting || replaceChildren.isPending || replaceChildren.isError || !fields.purpose.trim()} onClick={() => void startNarrative("focused")} type="button"><Sparkles aria-hidden size={20} />{starting ? "正在保存…" : record.narrative ? "按当前目标重新生成白描" : "确认并生成白描"}</button>
            {!record.child_id && <p className="mt-2 text-sm text-ink-muted">生成白描后，可根据衣着和行为对应幼儿姓名。</p>}
            {!fields.purpose.trim() && <p className="mt-2 text-sm text-ink-muted">有目标：先选择或添加目标；没有预设：先看看素材。</p>}
            <button className="mt-3 min-h-11 w-full text-base font-bold text-brand disabled:opacity-50" disabled={starting || replaceChildren.isPending || replaceChildren.isError} onClick={() => void startNarrative("explore")} type="button">先看看素材</button>
            <p className="mt-1 text-center text-xs text-ink-muted">暂不按目标聚焦，生成后再确认观察方向</p>
          </section>
        )}

        {(record.status === "processing" || generation.isPending) && (
          <section className="flex min-h-64 flex-col items-center justify-center rounded-2xl bg-white px-6 text-center shadow-sm">
            <LoaderCircle aria-hidden className="animate-spin text-brand" size={36} />
            <h2 className="mt-5 text-xl font-bold">{suggestTags.isPending ? "正在推荐指标…" : "正在生成白描…"}</h2>
            <p className="mt-2 text-sm leading-6 text-ink-muted">可以先返回首页，稍后再点进来看。</p>
            <Link className="mt-6 flex min-h-11 items-center px-5 font-bold text-brand" to="/">返回今日素材</Link>
          </section>
        )}

        {["ready_for_review", "confirmed"].includes(record.status) && (
          <div>
            {!inJudgment && <>
            <SectionHeading hint="AI 草拟 · 可直接改" title="白描记录" />
            <section className="rounded-2xl border border-stone-200 bg-white p-4">
              {editingNarrative ? (
                <textarea
                  autoFocus
                  className="min-h-80 w-full resize-y rounded-xl border border-brand/30 bg-stone-50 p-3 text-sm leading-7 outline-none focus:border-brand"
                  id="narrative"
                  onBlur={flushFields}
                  onChange={(event) => changeField("narrative", event.target.value)}
                  value={fields.narrative}
                />
              ) : (
                <button className="block w-full text-left" onClick={() => setEditingNarrative(true)} type="button">
                  <p className="whitespace-pre-wrap text-[15px] leading-8">{fields.narrative || "点击这里查看/修改白描"}</p>
                </button>
              )}
              <ChildNameInserter
                key={people.data?.narrative ?? fields.narrative}
                children={classroomChildren}
                people={fields.narrative === record.narrative ? people.data : undefined}
                loading={people.isFetching}
                error={people.isError}
                onRetry={() => void people.refetch()}
                onApply={async (assignments, narrative) => {
                  if (saveTimer.current) clearTimeout(saveTimer.current);
                  await saveQueue.current;
                  await replaceChildren.flush();
                  const result = await assignPeople.mutateAsync({ assignments, narrative });
                  const next = { ...fieldsRef.current, narrative: result.narrative };
                  fieldsRef.current = next;
                  setFields(next);
                  setIdentitySaved(true);
                }}
              />
              {identitySaved && <p className="mt-2 text-sm font-bold text-brand" role="status">姓名已代入并保存，观察对象已同步。</p>}
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

            {record.observation_mode === "explore" && !record.narrative_context_changed && fields.purpose.trim() && <button className="mt-3 min-h-11 w-full text-base font-bold text-brand disabled:opacity-50" disabled={starting} onClick={() => void startNarrative("focused")} type="button">按所选目标再看一次素材</button>}
            </>}

            {inJudgment && (
              <>
                <div className="mb-3 flex gap-2" aria-label="教师判断步骤">
                  <button className={`min-h-12 flex-1 rounded-xl border text-base font-bold ${!writing ? "border-brand bg-brand text-white" : "border-stone-300 bg-white text-brand"}`} onClick={() => setWriting(false)} type="button">1 选择指标</button>
                  <button className={`min-h-12 flex-1 rounded-xl border text-base font-bold disabled:opacity-50 ${writing ? "border-brand bg-brand text-white" : "border-stone-300 bg-white text-brand"}`} disabled={!acceptedTags.length || decideTag.isPending} onClick={() => setWriting(true)} type="button">2 分析与策略</button>
                </div>
                {!writing && <>
                <SectionHeading hint="至少采用一项" title="指标推荐" />
                <CandidateIndicators
                  addingTeacherTag={addTeacherTag.isPending}
                  indicatorOptions={indicators.data ?? []}
                  onAddTeacherTag={async (indicatorCode, level) => {
                    await addTeacherTag.mutateAsync({ indicatorCode, level });
                  }}
                  onDecide={(tagId, accepted) => decideTag.mutateAsync({ tagId, accepted })}
                  tags={record.tags}
                />

                </>}
                {writing && <>
                <p className="rounded-xl bg-brand-soft p-3 text-sm leading-6 text-brand-deep">已采用 {acceptedTags.length} 项：{acceptedTags.map((tag) => tag.indicator_name).join("、")}</p>
                <details className="mt-4"><summary className="min-h-11 cursor-pointer text-base font-bold text-brand">需要思路？查看 AI 建议</summary>
                <SectionHeading hint="思路支架 · 可改写" title="AI 建议" />
                <section className="rounded-2xl border border-[#cfe4d9] bg-[#f2f8f4] p-4">
                  {suggestAnalysis.data ? (
                    <div className="space-y-3">
                      {suggestAnalysis.data.is_mock && <p className="text-xs text-amber-700">{suggestAnalysis.data.notice}</p>}
                      <div>
                        <div className="mb-1.5 flex items-center justify-between gap-2">
                          <span className="text-sm font-bold text-brand-deep">观察分析（建议）</span>
                          <button aria-label="用这个分析改写我的分析" className="min-h-8 shrink-0 rounded-full border border-brand/40 px-3 text-xs font-bold text-brand" onClick={() => changeField("analysis", suggestAnalysis.data.analysis)} type="button">用这个改写</button>
                        </div>
                        <p className="whitespace-pre-wrap rounded-xl bg-white px-3 py-2 text-sm leading-7 text-ink">{suggestAnalysis.data.analysis}</p>
                      </div>
                      <div>
                        <div className="mb-1.5 flex items-center justify-between gap-2">
                          <span className="text-sm font-bold text-brand-deep">下一步支持策略（建议）</span>
                          <button aria-label="用这个策略改写我的措施" className="min-h-8 shrink-0 rounded-full border border-brand/40 px-3 text-xs font-bold text-brand" onClick={() => changeField("strategy", suggestAnalysis.data.strategy)} type="button">用这个改写</button>
                        </div>
                        <p className="whitespace-pre-wrap rounded-xl bg-white px-3 py-2 text-sm leading-7 text-ink">{suggestAnalysis.data.strategy}</p>
                      </div>
                      <p className="text-xs leading-5 text-ink-muted">AI 仅提供思路支架，请用「用这个改写」填入后再改写成你的判断。</p>
                      <button className="text-xs font-bold text-brand" onClick={() => suggestAnalysis.mutate()} type="button">重新生成</button>
                    </div>
                  ) : (
                    <button
                      className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl border border-brand text-sm font-bold text-brand disabled:opacity-60"
                      disabled={suggestAnalysis.isPending}
                      onClick={() => suggestAnalysis.mutate()}
                      type="button"
                    >
                      {suggestAnalysis.isPending ? "正在生成建议…" : "获取分析与策略建议"}
                    </button>
                  )}
                  {suggestAnalysis.isError && <p className="mt-2 text-sm text-red-700">AI 建议暂时没有生成成功，请再点一次</p>}
                </section>

                </details>
                <SectionHeading hint="必填" title="我的分析" />
                <section className="rounded-2xl border border-stone-200 bg-white p-4">
                  {acceptedTags.length > 0 && (
                    <div className="mb-3 flex flex-wrap gap-1.5">
                      {acceptedTags.map((tag) => (
                        <span className="rounded-full bg-brand-soft px-2.5 py-1 text-[11px] font-bold text-brand-deep" key={tag.id}>{tag.indicator_name}</span>
                      ))}
                    </div>
                  )}
                  <textarea
                    className="min-h-44 w-full resize-y rounded-xl border border-stone-200 bg-stone-50 p-3 text-base leading-7 outline-none focus:border-brand"
                    aria-label="我的分析"
                    required
                    id="analysis"
                    onBlur={flushFields}
                    onChange={(event) => changeField("analysis", event.target.value)}
                    placeholder="结合观察到的行为，写下你的专业判断"
                    value={fields.analysis}
                  />
                </section>

                <SectionHeading hint="必填" title="下一步支持策略" />
                <section className="rounded-2xl border border-stone-200 bg-white p-4">
                  <textarea
                    className="min-h-44 w-full resize-y rounded-xl border border-stone-200 bg-stone-50 p-3 text-base leading-7 outline-none focus:border-brand"
                    aria-label="下一步支持策略"
                    required
                    id="strategy"
                    onBlur={flushFields}
                    onChange={(event) => changeField("strategy", event.target.value)}
                    placeholder="下一步准备提供什么材料、提问或支持？"
                    value={fields.strategy}
                  />
                </section>
                </>}
              </>
            )}
          </div>
        )}

        {actionError && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{actionError}</p>}
        {updateObservation.isError && <p role="alert" className="mt-3 text-sm text-red-700">修改尚未保存，请重试后继续。</p>}
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

      {record.status === "ready_for_review" && !inJudgment && !record.narrative_context_changed && (
        <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200 bg-canvas/95 px-4 pt-3 backdrop-blur">
          <button
            className="min-h-14 w-full rounded-2xl bg-brand text-base font-bold text-white disabled:bg-stone-200 disabled:text-stone-400"
            disabled={!fields.narrative.trim() || !fields.purpose.trim() || !record.child_id || updateObservation.isPending || suggestTags.isPending || starting || replaceChildren.isPending || replaceChildren.isError || assignPeople.isPending}
            onClick={() => void continueToIndicators()}
            type="button"
          >
            {suggestTags.isPending ? "正在生成候选…" : "核对好了，推荐指标"}
          </button>
          <p className="mt-2 text-center text-xs text-ink-muted">先确认幼儿、观察目标和白描，再进入下一步</p>
        </div>
      )}

      {record.status === "ready_for_review" && inJudgment && (
        <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200 bg-canvas/95 px-4 pt-3 backdrop-blur">
          {record.child_id == null && (
            <p className="mb-2 text-center text-sm font-medium text-amber-700">请先选择这条记录关于哪位幼儿</p>
          )}
          {record.child_id != null && !fields.purpose.trim() && (
            <p className="mb-2 text-center text-sm font-medium text-amber-700">请至少选择或填写一个观察目标</p>
          )}
          {record.child_id != null && fields.purpose.trim() && acceptedTags.length === 0 && (
            <p className="mb-2 text-center text-sm font-medium text-amber-700">请至少采纳一个指标</p>
          )}
          <p className="mb-2 text-center text-sm font-bold text-brand" role="status">已采用 {acceptedTags.length} 项{decideTag.isPending ? " · 保存中…" : ""}</p>
          {writing && (!fields.analysis.trim() || !fields.strategy.trim()) && <p className="mb-2 text-center text-sm text-ink-muted">还需填写{!fields.analysis.trim() ? "观察分析" : ""}{!fields.analysis.trim() && !fields.strategy.trim() ? "和" : ""}{!fields.strategy.trim() ? "支持策略" : ""}</p>}
          {!writing ? <button className="min-h-14 w-full rounded-2xl bg-brand text-base font-bold text-white disabled:opacity-50" disabled={!acceptedTags.length || decideTag.isPending} onClick={() => { setWriting(true); window.scrollTo(0, 0); }} type="button">下一步：填写分析和策略</button> : <button
            className="min-h-14 w-full rounded-2xl bg-brand text-base font-bold text-white disabled:bg-stone-200 disabled:text-stone-400"
            disabled={record.child_id == null || !fields.purpose.trim() || acceptedTags.length === 0 || !fields.analysis.trim() || !fields.strategy.trim() || confirmation.isPending || decideTag.isPending}
            onClick={requestConfirmation}
            type="button"
          >
            {confirmation.isPending ? "正在生成完整稿…" : "确认记录，查看报告"}
          </button>
          }
          <p className="mt-2 text-center text-xs text-ink-muted">{writing ? "两项都填好后，确认并查看报告" : "选中状态会直接显示在指标卡上"}</p>
        </div>
      )}

      <div className="mt-6 border-t border-dashed border-[#ddd9cf] px-2 pt-5">
        <button
          className="flex min-h-12 w-full items-center justify-center gap-2 rounded-2xl border border-[#e3d0cc] bg-white py-3 text-sm font-medium text-[#b4453c] disabled:opacity-50"
          disabled={deleteObservation.isPending}
          onClick={() => { setDeleteError(""); setConfirmingDelete(true); }}
          type="button"
        >
          <Trash2 size={16} /> 删除这条记录
        </button>
        <p className="mt-2 text-center text-xs text-ink-muted">删除后连同素材、指标和 AI 记录一起清除，且不可恢复</p>
      </div>

      {record.status === "confirmed" && (
        <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200 bg-canvas/95 px-4 pt-3 backdrop-blur">
          <button
            className="min-h-14 w-full rounded-2xl bg-brand text-base font-bold text-white disabled:bg-stone-200 disabled:text-stone-400"
            disabled={!fields.analysis.trim() || !fields.strategy.trim() || updateObservation.isPending}
            onClick={() => void saveAndReturnToDetail()}
            type="button"
          >
            保存并返回完整稿
          </button>
          {!inJudgment && <button className="min-h-11 w-full text-base font-bold text-brand" onClick={() => setReviewingFacts(false)} type="button">查看指标与分析</button>}
        </div>
      )}

      {confirmingDelete && (
        <div className="fixed inset-0 z-30 flex items-end justify-center bg-black/35 p-4 sm:items-center" role="presentation">
          <section aria-labelledby="delete-prompt-heading" aria-modal="true" className="w-full max-w-sm rounded-3xl bg-white p-5 shadow-xl" role="dialog">
            <h2 className="text-xl font-bold" id="delete-prompt-heading">删除这条记录？</h2>
            <p className="mt-3 text-sm leading-6 text-ink-muted">会连同它绑定的素材、指标和 AI 记录一起删除，且不可恢复。</p>
            {deleteError && <p className="mt-2 text-sm text-red-700" role="alert">{deleteError}</p>}
            <div className="mt-6 grid grid-cols-2 gap-3">
              <button
                className="min-h-12 rounded-xl border border-[#dfdcd4] font-bold text-ink-muted"
                disabled={deleteObservation.isPending}
                onClick={() => setConfirmingDelete(false)}
                type="button"
              >
                取消
              </button>
              <button
                className="min-h-12 rounded-xl bg-[#b4453c] font-bold text-white disabled:opacity-60"
                disabled={deleteObservation.isPending}
                onClick={() => deleteObservation.mutate(undefined, {
                  onSuccess: () => navigate("/"),
                  onError: (err) => setDeleteError((err as Error).message),
                })}
                type="button"
              >
                {deleteObservation.isPending ? "删除中…" : "确认删除"}
              </button>
            </div>
          </section>
        </div>
      )}
    </MobilePage>
  );
}

function buildPurposePresets(): string[] {
  return ["观察幼儿如何选用与组合材料", "观察遇到困难后如何尝试和调整", "观察幼儿如何表达想法、与同伴协商", "观察幼儿怎样持续参与活动"];
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

/** 幼儿姓名胶囊：按幼儿 id 赋予稳定的区分色，弱化单调。 */
function ChildBadge({ childId, childLabel }: { childId: number | null; childLabel: string }) {
  const accent = childAccent(childId ?? 0);
  return (
    <span
      className="rounded-full px-2.5 py-1 text-xs font-bold"
      style={{ backgroundColor: accent.bg, color: accent.text }}
    >
      {childLabel}
    </span>
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
