import { Check, Plus } from "lucide-react";
import { useState } from "react";

function goalItems(value: string) {
  return [...new Set(value.split("\n").map((item) => item.trim()).filter(Boolean))];
}

/** 预设和自定义目标使用同一种多选方式，目标随当前记录保存。 */
export function ObservationGoals({ value, presets, onChange, disabled = false }: {
  value: string;
  presets: string[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const [custom, setCustom] = useState<string[]>([]);
  const selected = goalItems(value);
  const options = [...new Set([...presets, ...custom, ...selected])];
  function toggleGoal(goal: string) {
    if (!presets.includes(goal)) setCustom((previous) => [...new Set([...previous, goal])]);
    onChange((selected.includes(goal) ? selected.filter((item) => item !== goal) : [...selected, goal]).join("\n"));
  }
  function addGoal() {
    const items = goalItems(draft);
    if (!items.length) return;
    setCustom((previous) => [...new Set([...previous, ...items])]);
    onChange([...new Set([...selected, ...items])].join("\n"));
    setDraft("");
    setAdding(false);
  }
  return (
    <fieldset className="min-w-0 rounded-2xl border border-stone-200 bg-white p-4" disabled={disabled}>
      <legend className="sr-only">选择观察目标</legend>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-bold">这次想重点了解什么？</p>
        <span className="shrink-0 text-xs text-brand">已选 {selected.length} 个</span>
      </div>
      <p className="mb-3 mt-1 text-xs leading-5 text-ink-muted">可多选，建议 1～3 个，不限制上限</p>
      <div className="space-y-2">
        {options.map((goal) => (
          <button aria-pressed={selected.includes(goal)} className={`flex min-h-11 w-full items-start gap-2 rounded-xl border px-3 py-2.5 text-left text-base leading-6 ${selected.includes(goal) ? "border-brand bg-brand-soft text-brand-deep" : "border-stone-200 text-ink"}`} key={goal} onClick={() => toggleGoal(goal)} type="button">
            <span className="mt-1 flex size-4 shrink-0 items-center justify-center rounded-full border border-brand/40">{selected.includes(goal) && <Check aria-hidden size={13} />}</span>
            <span>{goal}</span>
          </button>
        ))}
      </div>
      {adding ? (
        <div className="mt-3">
          <label className="text-sm font-bold" htmlFor="new-observation-goal">新的观察目标</label>
          <textarea autoFocus className="mt-2 min-h-24 w-full rounded-xl border border-brand/40 p-3 text-base outline-none focus:border-brand" id="new-observation-goal" onChange={(event) => setDraft(event.target.value)} placeholder="例如：积木倒下后，他会怎样调整搭法？" value={draft} />
          <div className="mt-2 flex justify-end gap-3">
            <button className="min-h-11 px-3 text-base text-ink-muted" onClick={() => setAdding(false)} type="button">取消</button>
            <button className="min-h-11 rounded-xl bg-brand px-4 text-base font-bold text-white disabled:opacity-50" disabled={!draft.trim()} onClick={addGoal} type="button">添加并选中</button>
          </div>
        </div>
      ) : (
        <button className="mt-3 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-dashed border-brand/40 text-base font-bold text-brand" onClick={() => setAdding(true)} type="button"><Plus aria-hidden size={18} />添加观察目标</button>
      )}
    </fieldset>
  );
}
