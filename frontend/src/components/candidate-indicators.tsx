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
  onDecide: (tagId: number, accepted: boolean) => void;
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
          {acceptedCount > 0 ? `已采纳 ${acceptedCount} / ${recommendationCount}` : "勾选你认可的"}
        </p>
        <p className="text-xs text-ink-muted">把握程度只显示三档</p>
      </div>

      <div className="space-y-3">
        {systemTags.map((tag) => (
          <IndicatorCard
            dimension={dimensions.get(tag.indicator_code)}
            key={tag.id}
            onDecide={onDecide}
            systemDetermined
            tag={tag}
          />
        ))}
        {aiTags.map((tag) => (
          <IndicatorCard
            dimension={dimensions.get(tag.indicator_code)}
            key={tag.id}
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
              <div className="flex items-center justify-between rounded-xl bg-white px-3 py-3" key={tag.id}>
                <span className="text-sm font-bold">{tag.indicator_code} {tag.indicator_name}</span>
                <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-800">
                  {LEVEL_LABELS[tag.level] ?? `第 ${tag.level} 阶`}
                </span>
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
  onDecide,
  systemDetermined = false,
  tag,
}: {
  dimension?: string;
  onDecide: (tagId: number, accepted: boolean) => void;
  systemDetermined?: boolean;
  tag: ObservationTag;
}) {
  const accepted = tag.accepted === true;
  const rejected = tag.accepted === false;
  const confidence = confidencePresentation(tag, systemDetermined);

  return (
    <article className={`overflow-hidden rounded-2xl border bg-white ${accepted ? "border-brand/40 shadow-[0_0_0_2px_rgba(49,116,90,0.06)]" : "border-stone-200"}`}>
      <div className="p-4">
        <div className="flex items-start gap-3">
          <button
            aria-label={`采纳 ${tag.indicator_name}`}
            aria-pressed={accepted}
            className={`mt-0.5 grid size-5 shrink-0 place-items-center rounded-[5px] border ${accepted ? "border-brand bg-brand text-white" : "border-stone-300 bg-white text-transparent"}`}
            onClick={() => onDecide(tag.id, true)}
            type="button"
          >
            <Check size={13} strokeWidth={3} />
          </button>
          <div className="min-w-0 flex-1">
            <h3 className="text-[15px] font-bold leading-6">
              {tag.indicator_name}
              <span className="ml-2 inline-block rounded bg-stone-100 px-1.5 py-0.5 align-middle text-[10px] font-medium text-ink-muted">
                {dimension || (systemDetermined ? "系统判定" : "观察指标")}
              </span>
            </h3>
            <p className="mt-1 text-xs text-ink-muted">
              {tag.indicator_code} · {LEVEL_LABELS[tag.level] ?? `第 ${tag.level} 阶`}
            </p>
            <div className="mt-2 flex items-center gap-2 text-xs">
              <span className="text-ink-muted">把握程度</span>
              <span className="flex gap-1" aria-label={`${confidence.label}，三档中的 ${confidence.bars} 档`}>
                {[1, 2, 3].map((value) => (
                  <span className={`h-1.5 w-4 rounded-full ${value <= confidence.bars ? "bg-brand" : "bg-stone-200"}`} key={value} />
                ))}
              </span>
              <span className="font-bold text-brand">{confidence.label}</span>
            </div>
          </div>
        </div>

        <div className="mt-3 rounded-r-xl border-l-2 border-brand/20 bg-stone-50 px-3 py-2.5">
          <p className="text-[11px] text-stone-400">{systemDetermined ? "判定依据" : "对应原文"}</p>
          <p className="mt-1 text-[13px] leading-6 text-ink-muted">{tag.ai_reason || "基于客观数据判定，请结合原素材核对。"}</p>
        </div>

        <div className="mt-3 flex items-center justify-end gap-2">
          {accepted && <span className="mr-auto text-xs font-bold text-brand">已采纳</span>}
          {rejected && <span className="mr-auto text-xs font-bold text-stone-500">已标记为不采纳</span>}
          {systemDetermined ? (
            <button
              className="min-h-9 rounded-full border border-stone-300 px-3 text-xs font-bold text-ink-muted"
              onClick={() => onDecide(tag.id, !accepted)}
              type="button"
            >
              {accepted ? "取消采用" : "恢复采用"}
            </button>
          ) : (
            <>
              <button
                className={`min-h-9 rounded-full border px-3 text-xs font-bold ${accepted ? "border-brand bg-brand text-white" : "border-brand/40 text-brand"}`}
                onClick={() => onDecide(tag.id, true)}
                type="button"
              >
                采纳
              </button>
              <button
                className={`min-h-9 rounded-full border px-3 text-xs font-bold ${rejected ? "border-stone-600 bg-stone-600 text-white" : "border-stone-300 text-ink-muted"}`}
                onClick={() => onDecide(tag.id, false)}
                type="button"
              >
                不采纳
              </button>
            </>
          )}
        </div>
      </div>
    </article>
  );
}
