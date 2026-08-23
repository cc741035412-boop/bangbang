import { Check, ChevronDown, Minus, Plus, ShieldCheck, Sparkles } from "lucide-react";
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
    <div className="space-y-7">
      <section aria-labelledby="system-determined-heading" className="rounded-3xl border border-stone-300 bg-stone-100 p-4">
        <div className="flex items-start gap-3">
          <div className="grid size-10 shrink-0 place-items-center rounded-full bg-stone-200 text-stone-700">
            <ShieldCheck aria-hidden size={21} />
          </div>
          <div>
            <h2 className="text-lg font-bold" id="system-determined-heading">系统判定</h2>
            <p className="mt-1 text-sm leading-5 text-stone-600">基于视频时长等客观数据，不含推测</p>
          </div>
        </div>

        <div className="mt-4 space-y-3">
          {systemTags.map((tag) => {
            const selected = tag.accepted !== false;
            return (
              <button
                aria-pressed={selected}
                className={`flex min-h-16 w-full items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-left ${selected ? "border-stone-500 bg-white" : "border-stone-300 bg-stone-200/70 text-stone-500"}`}
                key={tag.id}
                onClick={() => onDecide(tag.id, !selected)}
                type="button"
              >
                <span>
                  <span className="block font-bold">{tag.indicator_code} {tag.indicator_name}</span>
                  <span className="mt-1 block text-sm">{LEVEL_LABELS[tag.level] ?? `第 ${tag.level} 阶`}</span>
                </span>
                <span className={`flex shrink-0 items-center gap-1 text-sm font-bold ${selected ? "text-stone-800" : "text-stone-500"}`}>
                  {selected ? <Check size={17} /> : <Minus size={17} />}
                  {selected ? "已选中" : "已取消"}
                </span>
              </button>
            );
          })}
          {systemTags.length === 0 && (
            <p className="rounded-2xl bg-white/70 px-4 py-4 text-sm text-stone-500">这段素材暂时没有可由客观数据直接判定的指标。</p>
          )}
        </div>
      </section>

      <section aria-labelledby="ai-suggested-heading">
        <div className="flex items-start gap-3 px-1">
          <div className="grid size-10 shrink-0 place-items-center rounded-full bg-indigo-100 text-indigo-700">
            <Sparkles aria-hidden size={20} />
          </div>
          <div>
            <h2 className="text-lg font-bold text-indigo-950" id="ai-suggested-heading">AI 建议，请你决定</h2>
            <p className="mt-1 text-sm leading-5 text-indigo-700">结合白描内容生成，必须由老师逐条判断</p>
          </div>
        </div>

        <div className="mt-4 space-y-4">
          {aiTags.map((tag) => {
            const confidence = tag.confidence ?? 0;
            const isLowConfidence = confidence <= 0.42;
            const isMediumConfidence = confidence > 0.42 && confidence < 0.7;
            const isRejected = tag.accepted === false;
            return (
              <article
                className={`rounded-3xl border p-4 ${isLowConfidence || isRejected ? "border-stone-200 bg-stone-100 text-stone-600" : "border-indigo-200 bg-white"} ${isLowConfidence ? "opacity-60" : ""}`}
                key={tag.id}
              >
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-bold">{tag.indicator_code} {tag.indicator_name}</h3>
                  <span className="shrink-0 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-bold text-indigo-700">
                    {LEVEL_LABELS[tag.level] ?? `第 ${tag.level} 阶`}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-6">{tag.ai_reason || "AI 暂未提供判断理由，请重点核对。"}</p>
                {isMediumConfidence && <p className="mt-3 text-xs font-bold text-amber-700">中等把握</p>}
                {isLowConfidence && (
                  <p className="mt-3 text-xs font-bold text-amber-800">⚠️ 仅依据区域先验推测，请重点核对</p>
                )}
                {tag.accepted === true && <p className="mt-3 text-sm font-bold text-emerald-700">已采纳</p>}
                {isRejected && <p className="mt-3 text-sm font-bold text-stone-500">已标记为“不是”</p>}
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <button
                    aria-pressed={tag.accepted === true}
                    className={`min-h-11 rounded-xl border font-bold ${tag.accepted === true ? "border-emerald-700 bg-emerald-700 text-white" : "border-emerald-700 bg-white text-emerald-700"}`}
                    disabled={tag.accepted === true}
                    onClick={() => onDecide(tag.id, true)}
                    type="button"
                  >
                    采纳
                  </button>
                  <button
                    aria-pressed={tag.accepted === false}
                    className={`min-h-11 rounded-xl border font-bold ${tag.accepted === false ? "border-stone-600 bg-stone-600 text-white" : "border-stone-300 bg-white text-stone-600"}`}
                    disabled={tag.accepted === false}
                    onClick={() => onDecide(tag.id, false)}
                    type="button"
                  >
                    不是
                  </button>
                </div>
              </article>
            );
          })}
          {aiTags.length === 0 && (
            <p className="rounded-2xl border border-indigo-100 bg-indigo-50 px-4 py-4 text-sm text-indigo-700">AI 没有找到足够可靠的候选指标，没有为了凑数而硬猜。</p>
          )}
        </div>

        <div className="mt-5 border-t border-stone-200 pt-5">
          <button
            aria-expanded={adding}
            className="flex min-h-11 w-full items-center justify-between rounded-2xl border border-dashed border-brand/40 bg-brand-soft/50 px-4 text-left font-bold text-brand-deep"
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
      </section>

      {teacherTags.length > 0 && (
        <section aria-labelledby="teacher-added-heading" className="rounded-3xl border border-emerald-200 bg-emerald-50 p-4">
          <h2 className="text-lg font-bold text-emerald-950" id="teacher-added-heading">你补充的</h2>
          <p className="mt-1 text-sm text-emerald-800">这些是 AI 没有想到、由你判断应保留的指标</p>
          <div className="mt-4 space-y-2">
            {teacherTags.map((tag) => (
              <div className="flex items-center justify-between rounded-2xl bg-white px-4 py-3" key={tag.id}>
                <span className="font-bold">{tag.indicator_code} {tag.indicator_name}</span>
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
