import { ArrowLeft, LoaderCircle, RotateCcw, Sparkles } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { CandidateIndicators } from "../components/candidate-indicators";
import { MediaThumbnail } from "../components/media-thumbnail";
import { MobilePage } from "../components/mobile-page";
import {
  useGenerateNarrative,
  useDecideTag,
  useObservation,
  useSaveNarrative,
  useSuggestTags,
} from "../features/observations/api";
import { formatKindergartenTime } from "../lib/date-time";

function humanizeFailure(reason?: string | null) {
  if (!reason) return "这次没有整理成功，请重新试一次";
  if (/素材|绑定/.test(reason)) return "素材还没有准备好，请返回首页确认后再试";
  if (/网络|timeout|timed out|connection/i.test(reason)) return "网络不太稳定，这次没有整理完成，请重新试一次";
  return "这次没有整理成功，请重新试一次";
}

export function ObservationReviewPage() {
  const { observationId } = useParams();
  const id = Number(observationId);
  const observation = useObservation(id);
  const generation = useGenerateNarrative(id);
  const saveNarrative = useSaveNarrative(id);
  const suggestTags = useSuggestTags(id);
  const decideTag = useDecideTag(id);
  const [draft, setDraft] = useState("");
  const initializedKey = useRef("");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const record = observation.data;
  const candidateTags = record?.tags.filter((tag) => (
    tag.source === "system_determined" || tag.source === "ai_suggested"
  )) ?? [];
  const showIndicators = candidateTags.length > 0 || suggestTags.isSuccess;

  useEffect(() => {
    if (!record || record.status !== "ready_for_review") return;
    const key = `${record.id}:${record.ready_at ?? "ready"}`;
    if (initializedKey.current !== key) {
      initializedKey.current = key;
      setDraft(record.narrative ?? "");
    }
  }, [record]);

  const isMock = generation.data?.is_mock === true
    || (Number.isInteger(id) && sessionStorage.getItem(`narrative-is-mock:${id}`) === "true");

  function save(value: string) {
    if (!record || value === (record.narrative ?? "")) return;
    saveNarrative.mutate(value);
  }

  function changeNarrative(value: string) {
    setDraft(value);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => save(value), 700);
  }

  function flushNarrative() {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = null;
    save(draft);
  }

  async function continueToIndicators() {
    if (!record) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = null;
    try {
      if (draft !== (record.narrative ?? "")) {
        await saveNarrative.mutateAsync(draft);
      }
      suggestTags.mutate();
    } catch {
      // 保存错误已由页面状态提示；白描未落库时不能基于旧内容生成候选。
    }
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
            onClick={flushNarrative}
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
              onBlur={flushNarrative}
              onChange={(event) => changeNarrative(event.target.value)}
              value={draft}
            />
            <div className="mt-2 min-h-5 text-xs text-ink-muted" role="status">
              {saveNarrative.isPending && "正在自动保存…"}
              {saveNarrative.isSuccess && !saveNarrative.isPending && "已自动保存"}
              {saveNarrative.isError && "暂时没有保存成功，继续修改或离开输入框会重试"}
            </div>
            {isMock && (
              <p className="mt-3 text-xs leading-5 text-stone-500">⚠️ 当前为演示数据，尚未接入真实 AI</p>
            )}
          </section>
        )}

        {record.status === "ready_for_review" && showIndicators && (
          <CandidateIndicators
            onDecide={(tagId, accepted) => decideTag.mutate({ tagId, accepted })}
            tags={candidateTags}
          />
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
      </div>

      {record.status === "ready_for_review" && !showIndicators && (
        <div className="safe-bottom fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-[430px] border-t border-stone-200/70 bg-canvas/95 px-5 pt-3">
          <button
            className="min-h-14 w-full rounded-2xl bg-brand text-lg font-bold text-white disabled:bg-stone-200 disabled:text-stone-400"
            disabled={!draft.trim() || saveNarrative.isPending || suggestTags.isPending}
            onClick={() => void continueToIndicators()}
            type="button"
          >
            {suggestTags.isPending ? "正在生成候选…" : "下一步"}
          </button>
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
