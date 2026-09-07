import { useState } from "react";
import type { ObservationPeople, PersonAssignment, PersonGroup } from "../features/observations/api";

/** 按人物对应姓名；整组引用一次保存，群体称呼保持原文。 */
export function ChildNameInserter({ people, children, loading, error, onRetry, onApply }: {
  people?: ObservationPeople;
  children: { id: number; name: string }[];
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  onApply: (assignments: PersonAssignment[], narrative: string) => Promise<void>;
}) {
  const [splitGroups, setSplitGroups] = useState<number[]>([]);
  const [assignments, setAssignments] = useState<Record<number, number>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  if (loading) return <p className="mt-4 text-sm text-brand" role="status">正在根据白描整理人物线索…</p>;
  if (error) return <div className="mt-4 text-sm text-red-700"><p>人物整理暂未完成，白描仍可编辑。</p><button className="min-h-11 text-base font-bold underline" onClick={onRetry} type="button">重新整理人物</button></div>;
  if (!people) return null;
  if (!people.people.length) return <p className="mt-4 text-sm text-ink-muted">没有待对应的个人称呼。请核对白描中的姓名及上方观察对象。</p>;
  const groups: PersonGroup[] = people.people.flatMap((group, i) => splitGroups.includes(i)
    ? group.ref_indexes.map((index) => ({ label: group.label, ref_indexes: [index], clues: [people.refs[index]?.clue ?? "请核对原文"] })) : [group]);
  const chosen = groups.filter((group) => assignments[(group.ref_indexes[0] ?? -1)]);
  async function apply() {
    if (!people) return;
    setSaving(true); setSaveError("");
    try {
      await onApply(chosen.map((group) => ({ ref_indexes: group.ref_indexes, child_id: assignments[(group.ref_indexes[0] ?? -1)] ?? 0 })), people.narrative);
    } catch (err) { setSaveError(err instanceof Error ? err.message : "姓名未保存，请重试"); }
    finally { setSaving(false); }
  }
  return (
    <section className="mt-4 rounded-2xl border border-brand/25 bg-brand-soft p-3" aria-label="按人物对应姓名">
      <h3 className="text-base font-bold text-brand-deep">白描中可能有 {groups.length} 位待对应的幼儿</h3>
      <p className="mt-1 text-sm leading-6 text-ink-muted">对照衣着、行为选姓名，同一人物只选一次。</p>
      <p className="mt-1 text-sm leading-6 text-ink-muted">{people.notice}</p>
      <div className="mt-3 space-y-3">
        {groups.map((group, i) => (
          <div className="rounded-xl bg-white p-3" key={group.ref_indexes.join(",")}>
            <label className="text-base font-bold" htmlFor={`person-${i}`}>人物 {i + 1}</label>
            <p className="mt-1 text-sm leading-6 text-ink-muted">{group.clues[0]}</p>
            {group.clues.length > 1 && <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-brand">更多行为线索</summary>{group.clues.slice(1).map((clue) => <p className="mb-2 text-sm leading-6" key={clue}>{clue}</p>)}</details>}
            <select className="mt-2 min-h-12 w-full rounded-xl border border-stone-300 bg-white px-3 text-base" id={`person-${i}`} disabled={saving} value={assignments[(group.ref_indexes[0] ?? -1)] ?? ""} onChange={(e) => setAssignments((current) => ({ ...current, [(group.ref_indexes[0] ?? -1)]: Number(e.target.value) }))}>
              <option value="">选择姓名（暂不确定可留空）</option>
              {children.map((child) => <option key={child.id} value={child.id}>{child.name}</option>)}
            </select>
            <p className="mt-1 text-sm text-ink-muted">将一起代入 {group.ref_indexes.length} 处称呼</p>
          </div>
        ))}
      </div>
      <details className="mt-2"><summary className="min-h-11 cursor-pointer py-2 text-sm text-brand">分组不对？拆开核对</summary><p className="text-sm leading-6 text-ink-muted">同一个人被分成两组时，两组选择同一姓名即可。不同人被合并时，可拆开。</p>{people.people.map((group, i) => group.ref_indexes.length > 1 && !splitGroups.includes(i) && <button type="button" disabled={saving} className="mr-2 min-h-11 text-base font-bold text-brand" key={i} onClick={() => { setSplitGroups((current) => [...current, i]); setAssignments((current) => Object.fromEntries(Object.entries(current).filter(([key]) => !group.ref_indexes.includes(Number(key))))); }}>拆开{group.label}</button>)}</details>
      <button className="mt-2 min-h-12 w-full rounded-xl bg-brand text-base font-bold text-white disabled:opacity-50" type="button" disabled={!chosen.length || saving} onClick={() => void apply()}>{saving ? "正在代入并保存…" : "确认人物并代入姓名"}</button>
      {people.refs.some((ref) => ref.group) && <p className="mt-2 text-sm text-ink-muted">“孩子们”等群体称呼会保留。</p>}
      {saveError && <p className="mt-2 text-sm text-red-700" role="alert">{saveError}</p>}
    </section>
  );
}
