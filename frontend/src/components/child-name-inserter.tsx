import { ChevronDown, UserRound } from "lucide-react";
import { useMemo, useState } from "react";

import { applyChildNames, distinctPersonRefs, findPersonRefs, isGroupRef } from "../lib/substitute-children";

/**
 * 白描"代入幼儿名"面板。
 *
 * - 记录只有一个幼儿 → 一键把白描里的非群体泛称（女童/男童/幼儿…）代入该幼儿姓名；
 * - 多个幼儿 → 每个非群体泛称由老师指认到某个幼儿，逐个代入；
 * - 群体泛称（孩子们/小朋友们…）默认"可跳过"，不强迫指认到单个名字；
 * - 允许只代入一部分：未指认的保留原泛称，不影响继续生成指标。
 * 代入发生在本地（姓名从不发给模型），替换后的文本仍可直接编辑。
 */
export function ChildNameInserter({
  text,
  children,
  selectedChildId,
  onApply,
}: {
  text: string;
  children: { id: number; name: string }[];
  selectedChildId?: number | null;
  onApply: (newText: string) => void;
}) {
  const refs = useMemo(() => findPersonRefs(text), [text]);
  const [open, setOpen] = useState(false);
  const [assignments, setAssignments] = useState<Record<number, string>>({});

  if (refs.length === 0) return null;

  const selectedChild = children.find((c) => c.id === selectedChildId) ?? null;
  const distinct = distinctPersonRefs(text);
  const groupCount = refs.filter((r) => isGroupRef(text, r)).length;
  const individualRefs = refs.map((r, i) => ({ ref: r, i })).filter((x) => !isGroupRef(text, x.ref));
  const hasAnyAssignment = individualRefs.some(({ i }) => assignments[i]);
  const refContext = (i: number) => {
    const start = Math.max(0, refs[i].index - 16);
    return text.slice(start, refs[i].index + refs[i].length + 8);
  };

  // 代入时跳过群体泛称（含"几名孩子/一群孩子/三四个孩子"这类带数量词的），避免被硬改成一个名字。
  const skipGroups = (map: (refIndex: number) => string) =>
    refs.map((ref, i) => (isGroupRef(text, ref) ? "" : map(i)));

  function applyAll() {
    onApply(applyChildNames(text, refs, skipGroups(() => selectedChild?.name ?? "")));
  }

  function applyMapped() {
    onApply(applyChildNames(text, refs, skipGroups((i) => assignments[i])));
  }

  return (
    <div className="mt-3 rounded-2xl border border-[#cfe4d9] bg-[#f2f8f4] px-4 py-3">
      <button
        type="button"
        className="flex w-full items-center gap-2 text-left text-sm font-semibold text-brand-deep"
        onClick={() => setOpen((v) => !v)}
      >
        <UserRound size={16} />
        {selectedChild
          ? `白描里有 ${refs.length} 处写的是泛称，可代入幼儿名「${selectedChild.name}」`
          : `白描里有 ${refs.length} 处是泛称，可指认到幼儿`}
        <ChevronDown className={`ml-auto transition-transform ${open ? "rotate-180" : ""}`} size={16} />
      </button>

      {open && (
        <div className="mt-3 space-y-2">
          <p className="text-xs leading-5 text-ink-muted">
            检测到的人物泛称（{refs.length} 处）：{distinct.join("、")}
            {groupCount > 0 && `（其中 ${groupCount} 处为群体，可跳过）`}。
            姓名只在本地代入，不会发送给 AI。
          </p>

          {selectedChild && groupCount === 0 && (
            <button
              type="button"
              className="w-full min-h-10 rounded-xl bg-brand font-bold text-white disabled:bg-[#c2cec9]"
              onClick={applyAll}
            >
              一键代入「{selectedChild.name}」
            </button>
          )}

          {selectedChild && groupCount > 0 && (
            <p className="rounded-xl bg-[#eef5f0] px-3 py-2 text-xs leading-5 text-ink-muted">
              这段提到了多个孩子，为避免把不同的人写成同一个名字，请逐个指认下面的个体（群体已可跳过）。
            </p>
          )}

          {!selectedChild && (
            <p className="text-xs text-amber-700">请先在上方选择这条记录关于哪位幼儿，再逐处指认。</p>
          )}

          <ul className="space-y-1.5">
            {refs.map((ref, i) => {
              const isGroup = isGroupRef(text, ref);
              return (
                <li key={i} className="flex items-center gap-2 text-sm">
                  <span className="min-w-0 flex-1 truncate text-ink-muted">
                    第 {i + 1} 处「{ref.token}」…{refContext(i)}
                  </span>
                  {isGroup ? (
                    <span className="shrink-0 rounded-lg bg-[#e7efe9] px-2 py-1 text-xs text-ink-muted">群体 · 可跳过</span>
                  ) : (
                    <select
                      aria-label={`第 ${i + 1} 处泛称指认幼儿`}
                      className="max-w-[9rem] shrink-0 rounded-xl border border-[#dfdcd4] bg-white px-2 py-1.5 text-sm outline-none focus:border-brand"
                      onChange={(e) => setAssignments((a) => ({ ...a, [i]: e.target.value }))}
                      value={assignments[i] ?? ""}
                    >
                      <option value="">选择幼儿</option>
                      {children.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
                    </select>
                  )}
                </li>
              );
            })}
          </ul>

          {selectedChild && individualRefs.length > 0 && (
            <p className="text-xs text-ink-muted">
              已选 {Object.keys(assignments).filter((k) => assignments[Number(k)]).length} 处，可继续生成指标；未选的保留原泛称。
            </p>
          )}

          {selectedChild && refs.length > 1 && (
            <button
              type="button"
              className="w-full min-h-10 rounded-xl border border-brand font-bold text-brand disabled:bg-[#c2cec9] disabled:text-stone-400"
              disabled={!hasAnyAssignment}
              onClick={applyMapped}
            >
              应用上面的逐处指认
            </button>
          )}
        </div>
      )}
    </div>
  );
}
