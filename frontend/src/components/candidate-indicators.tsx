import { Check, ChevronDown, Plus } from "lucide-react";
import { useMemo, useState } from "react";

import type { IndicatorOption, ObservationTag } from "../features/observations/api";

const LEVEL_LABELS: Record<number, string> = {
  1: "初阶",
  2: "中阶",
  3: "高阶",
};

interface CandidateIndicatorsProps {
  addingTeacherTag: boolean;
  indicatorOptions: IndicatorOption[];
  onAddTeacherTag: (indicatorCode: string, level: number) => Promise<void>;
  onDecide: (tagId: number, accepted: boolean) => Promise<unknown> | void;
  tags: ObservationTag[];
}

export function CandidateIndicators({
  addingTeacherTag,
  indicatorOptions,
  onAddTeacherTag,
  onDecide,
  tags,
}: CandidateIndicatorsProps) {
  const [adding, setAdding] = useState(false);
  const [indicatorCode, setIndicatorCode] = useState("");
  const [level, setLevel] = useState(1);
  const systemTags = tags.filter((tag) => tag.source === "system_determined");
  const aiTags = tags
    .filter((tag) => tag.source === "ai_suggested")
    .sort((a, b) => (a.rank_in_suggestion ?? 99) - (b.rank_in_suggestion ?? 99));
  const teacherTags = tags.filter((tag) => tag.source === "teacher_added");
  const indicators = useMemo(() => {
    const unique = new Map<string, IndicatorOption>();
    indicatorOptions.forEach((item) => unique.set(item.indicator_code, item));
    return [...unique.values()];
  }, [indicatorOptions]);
  const dimensions = useMemo(() => {
    const map = new Map<string, string>();
    indicatorOptions.forEach((item) => map.set(item.indicator_code, item.dimension));
    return map;
  }, [indicatorOptions]);
  // 每个 (指标编号, 层级) 的行为发展锚点描述，读自指标体系。
  const levelDesc = useMemo(() => {
    const map = new Map<string, string>();
    indicatorOptions.forEach((item) => map.set(`${item.indicator_code}:${item.level}`, item.description));
    return map;
  }, [indicatorOptions]);
  const recommendationCount = systemTags.length + aiTags.length;
  const acceptedCount = [...systemTags, ...aiTags].filter((tag) => tag.accepted === true).length;

  async function addTeacherTag() {
    if (!indicatorCode) return;
    try {
      await onAddTeacherTag(indicatorCode, level);
      setIndicatorCode("");
      setLevel(1);
      setAdding(false);
    } catch {
      // 页面统一显示保存错误；保留当前选择，教师可直接重试。
    }
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between px-0.5">
        <p className="text-xs text-ink-muted">
          {acceptedCount > 0 ? `已采用 ${acceptedCount} / ${recommendationCount}` : "选择你认可的指标"}
        </p>

      </div>

      <div className="space-y-3">
        {systemTags.map((tag) => (
          <IndicatorCard
            dimension={dimensions.get(tag.indicator_code)}
            key={tag.id}
            levelDesc={levelDesc.get(`${tag.indicator_code}:${tag.level}`)}
            onDecide={onDecide}
            systemDetermined
            tag={tag}
          />
        ))}
        {aiTags.map((tag) => (
          <IndicatorCard
            dimension={dimensions.get(tag.indicator_code)}
            key={tag.id}
            levelDesc={levelDesc.get(`${tag.indicator_code}:${tag.level}`)}
            onDecide={onDecide}
            tag={tag}
          />
        ))}
        {recommendationCount === 0 && (
          <p className="rounded-2xl border border-stone-200 bg-white px-4 py-5 text-sm leading-6 text-ink-muted">
            没有找到足够可靠的候选指标，没有为了凑数而硬猜。
          </p>
        )}
      </div>

      <div className="mt-4">
          <button
            aria-expanded={adding}
            className="flex min-h-11 w-full items-center justify-between rounded-2xl border border-dashed border-brand/40 bg-white px-4 text-left text-sm font-bold text-brand-deep"
            onClick={() => setAdding((value) => !value)}
            type="button"
          >
            <span className="flex items-center gap-2"><Plus size={18} /> 都没说到？我自己加一条</span>
            <ChevronDown className={adding ? "rotate-180" : ""} size={18} />
          </button>

        {adding && (
            <div className="mt-3 space-y-4 rounded-2xl border border-brand/20 bg-white p-4">
              <label className="block text-sm font-bold" htmlFor="teacher-indicator">选择指标</label>
              <select
                className="min-h-12 w-full rounded-xl border border-stone-300 bg-white px-3 text-base"
                id="teacher-indicator"
                onChange={(event) => setIndicatorCode(event.target.value)}
                value={indicatorCode}
              >
                <option value="">请选择一项</option>
                {indicators.map((item) => (
                  <option key={item.indicator_code} value={item.indicator_code}>
                    {item.indicator_code} {item.indicator_name}
                  </option>
                ))}
              </select>

              <fieldset>
                <legend className="text-sm font-bold">选择层级</legend>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  {[1, 2, 3].map((value) => (
                    <button
                      aria-pressed={level === value}
                      className={`min-h-11 rounded-xl border text-sm font-bold ${level === value ? "border-brand bg-brand text-white" : "border-stone-300 bg-white text-stone-600"}`}
                      key={value}
                      onClick={() => setLevel(value)}
                      type="button"
                    >
                      {LEVEL_LABELS[value]}
                    </button>
                  ))}
                </div>
              </fieldset>

              <button
                className="min-h-12 w-full rounded-xl bg-brand font-bold text-white disabled:bg-stone-200 disabled:text-stone-400"
                disabled={!indicatorCode || addingTeacherTag}
                onClick={() => void addTeacherTag()}
                type="button"
              >
                {addingTeacherTag ? "正在保存…" : "确认补充"}
              </button>
            </div>
          )}
      </div>

      {teacherTags.length > 0 && (
        <section aria-labelledby="teacher-added-heading" className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
          <h2 className="text-base font-bold text-emerald-950" id="teacher-added-heading">你补充的</h2>
          <div className="mt-3 space-y-2">
            {teacherTags.map((tag) => (
              <div className="rounded-xl bg-white px-3 py-3" key={tag.id}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold">{tag.indicator_code} {tag.indicator_name}</span>
                  <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-800">
                    {LEVEL_LABELS[tag.level] ?? `第 ${tag.level} 阶`}
                  </span>
                </div>
                {levelDesc.get(`${tag.indicator_code}:${tag.level}`) && (
                  <p className="mt-1.5 rounded-lg bg-[#f2f8f2] px-2 py-1.5 text-xs leading-5 text-ink-muted">
                    {LEVEL_LABELS[tag.level] ?? `第 ${tag.level} 阶`}锚点：{levelDesc.get(`${tag.indicator_code}:${tag.level}`)}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function confidencePresentation(tag: ObservationTag, systemDetermined: boolean) {
  if (systemDetermined) return { bars: 3, label: "客观判定" };
  const confidence = tag.confidence ?? 0;
  if (confidence >= 0.7) return { bars: 3, label: "较有把握" };
  if (confidence > 0.42) return { bars: 2, label: "有一些把握" };
  return { bars: 1, label: "把握不大" };
}

function IndicatorCard({
  dimension,
  levelDesc,
  onDecide,
  systemDetermined = false,
  tag,
}: {
  dimension?: string;
  levelDesc?: string;
  onDecide: (tagId: number, accepted: boolean) => Promise<unknown> | void;
  systemDetermined?: boolean;
  tag: ObservationTag;
}) {
  const [pending, setPending] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const decision = pending ?? tag.accepted;
  const accepted = decision === true;
  const rejected = decision === false;
  const confidence = confidencePresentation(tag, systemDetermined);
  async function decide(value: boolean) {
    setPending(value); setError("");
    try { await onDecide(tag.id, value); }
    catch { setError("没有保存成功，请再选一次。"); }
    finally { setPending(null); }
  }
  return (
    <article aria-label={tag.indicator_name} className={`rounded-2xl border-2 p-4 ${accepted ? "border-brand bg-brand-soft" : "border-stone-200 bg-white"}`}>
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="text-ink-muted">{systemDetermined ? "系统计算" : "AI 建议"}</span>
        <span role="status" className={`flex items-center gap-1 font-bold ${accepted ? "text-brand-deep" : "text-ink-muted"}`}>
          {accepted && <Check size={18} />}{pending !== null ? (accepted ? "已选，保存中…" : "保存中…") : accepted ? "已采用" : rejected ? "已不采用" : "待选择"}
        </span>
      </div>
      <h3 className="mt-2 text-lg font-bold">{tag.indicator_name}</h3>
      <p className="mt-1 text-sm text-ink-muted">{LEVEL_LABELS[tag.level] ?? `第 ${tag.level} 阶`}{dimension ? ` · ${dimension}` : ""}</p>
      <details className="mt-2">
        <summary className="min-h-11 cursor-pointer py-2 text-base font-bold text-brand">查看依据与层级</summary>
        <p className="text-sm leading-7">{tag.ai_reason || "请结合原素材核对。"}</p>
        {levelDesc && <p className="mt-2 text-sm leading-7 text-ink-muted">层级说明：{levelDesc}</p>}
        <p className="mt-2 text-sm text-ink-muted">{tag.indicator_code} · {confidence.label}</p>
      </details>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button aria-label={`采用 ${tag.indicator_name}`} aria-pressed={accepted} className={`min-h-12 rounded-xl border text-base font-bold disabled:opacity-60 ${accepted ? "border-brand bg-brand text-white" : "border-brand text-brand"}`} disabled={pending !== null} onClick={() => void decide(true)} type="button">{accepted ? "已采用" : "采用这个指标"}</button>
        <button aria-label={`不采用 ${tag.indicator_name}`} aria-pressed={rejected} className={`min-h-12 rounded-xl border text-base font-bold disabled:opacity-60 ${rejected ? "border-stone-600 bg-stone-600 text-white" : "border-stone-300 bg-white text-ink-muted"}`} disabled={pending !== null} onClick={() => void decide(false)} type="button">{rejected ? "已不采用" : "不采用"}</button>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
    </article>
  );
}
