import { Check, Minus, ShieldCheck, Sparkles } from "lucide-react";

import type { ObservationTag } from "../features/observations/api";

const LEVEL_LABELS: Record<number, string> = {
  1: "初阶",
  2: "中阶",
  3: "高阶",
};

interface CandidateIndicatorsProps {
  onDecide: (tagId: number, accepted: boolean) => void;
  tags: ObservationTag[];
}

export function CandidateIndicators({ onDecide, tags }: CandidateIndicatorsProps) {
  const systemTags = tags.filter((tag) => tag.source === "system_determined");
  const aiTags = tags
    .filter((tag) => tag.source === "ai_suggested")
    .sort((a, b) => (a.rank_in_suggestion ?? 99) - (b.rank_in_suggestion ?? 99));

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
      </section>
    </div>
  );
}
