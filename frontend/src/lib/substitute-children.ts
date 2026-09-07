/**
 * 白描里的人物泛称识别与"代入幼儿名"。
 *
 * 背景：豆包生成白描时按隐私规则只用泛称（左侧女童/中间男童/幼儿…），
 * 不把真实姓名发给模型。这里在本地、生成之后，把泛称替换成幼儿姓名。
 *
 * 规则（方案 B）：
 *  - 记录只属于一个幼儿 → 可一键把全部泛称代入该幼儿姓名；
 *  - 多个幼儿 → 每个泛称可由老师"指认"到某个幼儿，逐个代入。
 */

export interface PersonRef {
  /** 在原文中的起始下标 */
  index: number;
  /** 泛称长度 */
  length: number;
  /** 泛称原文，如 "女童" */
  token: string;
}

/** 按"最长优先、不重叠"扫描，避免 小朋友们/小朋友、幼儿们/幼儿 这类重复命中。 */
const WORDS = [
  "小朋友们", "孩子们", "幼儿们", "各位幼儿",
  "小朋友", "女童", "男童", "女孩", "男孩",
  "幼儿", "孩童", "儿童", "孩子", "小孩",
];

/** 群体性泛称：指代"一群孩子"，无法也无须指认到单个幼儿姓名。 */
export const GROUP_WORDS = new Set(["小朋友们", "孩子们", "幼儿们", "各位幼儿"]);

/** 后端把幼儿姓名匿名成"幼儿A / 幼儿B / 幼儿AA…"这样的别名（_child_alias）。
 *  这是"一个人"的整体，必须整体识别，否则会把"幼儿A"误拆成泛称"幼儿"+字母。 */
const ALIAS_RE = /幼儿([A-Za-z]+)/y;
const ALIAS_TOKEN_RE = /^幼儿[A-Za-z]+$/;

export function isAliasToken(token: string): boolean {
  return ALIAS_TOKEN_RE.test(token);
}

export function isGroupToken(token: string): boolean {
  return GROUP_WORDS.has(token);
}

// 紧贴泛称之前的"数量 + 类别词"，用于识别"几名孩子/一群孩子/三四个孩子/许多孩子"这类群体表达。
// 注意：刻意不含单独"一"作数（排除"一个/一名"这种单数）；序数"第X个"另行排除。
// 关键：整个备选必须用 (?:...) 括起来，否则后面的 (?:的)?$ 只锚定最后一个备选，
//      导致"几/很多/一群…"会在任意位置命中（这是之前全部误判成群体的根因）。
const GROUP_QUANT_RE = new RegExp(
  "(?:" + [
    "[两二三四五六七八九十百千\\d]+(?:个|名|位|群|批|帮|十来名?)",  // 两三个/三四个/五六个/十几名/二十几…
    "几(?:个|名|位|群|些|十名?)",                                   // 几个/几名/几位/几群/几十名
    "一(?:群|些|批|帮)",                                            // 一群/一些/一批
    "好几(?:个|名|位|群|些)?",                                      // 好几个/好几名
    "许多|很多|不少|若干|众多|所有|全部|全体|有的|有些|更多|好些|无数|一堆|大批",  // 许多/更多/好些/一堆/大批孩子…
    "这(?:些|群)|那(?:些|群)|各位",
    "成(?:群|批|帮)",
  ].join("|") + ")(?:的)?$"
);

/**
 * 判断某个泛称是否属于"群体"：
 * - 复数泛称（孩子们/小朋友们…）直接判为群体；
 * - 或紧贴其前的上下文是"数量+类别词、一群/一些/很多/所有…"，如"几名孩子、一群孩子、三四个孩子"。
 * 序数"第X个"（单数）会排除。
 */
export function isGroupRef(text: string, ref: { index: number; token: string }): boolean {
  if (GROUP_WORDS.has(ref.token)) return true;
  // 只取紧贴词尾的一小段，避免无关前缀干扰；并强制匹配必须"贴到词尾"。
  const tail = text.slice(Math.max(0, ref.index - 8), ref.index);
  const m = GROUP_QUANT_RE.exec(tail);
  if (!m) return false;
  if (m.index + m[0].length !== tail.length) return false;  // 必须紧贴"孩子"之前
  if (tail[m.index - 1] === "第") return false;             // 排除"第X个"序数
  return true;
}

export function findPersonRefs(text: string, knownNames: string[] = []): PersonRef[] {
  const refs: PersonRef[] = [];
  const names = knownNames.filter(Boolean).sort((a, b) => b.length - a.length);
  let i = 0;
  while (i < text.length) {
    // 已经代入的完整姓名不可再次作为泛称替换。
    const name = names.find((item) => text.startsWith(item, i));
    if (name) {
      i += name.length;
      continue;
    }
    // 先整体识别匿名别名（幼儿A / 幼儿B…），避免被拆成「幼儿」+字母
    ALIAS_RE.lastIndex = i;
    const alias = ALIAS_RE.exec(text);
    if (alias) {
      refs.push({ index: i, length: alias[0].length, token: alias[0] });
      i += alias[0].length;
      continue;
    }
    let matched = false;
    for (const w of WORDS) {
      if (text.startsWith(w, i)) {
        refs.push({ index: i, length: w.length, token: w });
        i += w.length;
        matched = true;
        break;
      }
    }
    if (!matched) i += 1;
  }
  return refs;
}

/**
 * 把白描的"人物引用"归组为"逻辑上的人"。
 *  - 别名（幼儿A / 幼儿B…）同一字母是同一人 → 合并为一个槽位，一次指认即代入全部出现处；
 *  - 泛称（女童/男童/幼儿…）同一词可能指不同的人 → 每次出现各为一个槽位（保持原逐处指认语义）。
 * 用于避免"白描里其实是同一个幼儿A"却让老师逐处选 4 遍的困惑。
 */
export interface PersonSlot {
  token: string;
  /** 在 refs（findPersonRefs 结果）里的出现下标，全部要代入同一个名字 */
  refIndexes: number[];
  isAlias: boolean;
  isGroup: boolean;
}

export function groupPersonRefs(text: string, refs: PersonRef[]): PersonSlot[] {
  const slots: PersonSlot[] = [];
  const aliasSlotIndex = new Map<string, number>();
  refs.forEach((ref, i) => {
    if (isAliasToken(ref.token)) {
      const existing = aliasSlotIndex.get(ref.token);
      const slot = existing === undefined ? undefined : slots[existing];
      if (slot) {
        slot.refIndexes.push(i);
      } else {
        aliasSlotIndex.set(ref.token, slots.length);
        slots.push({ token: ref.token, refIndexes: [i], isAlias: true, isGroup: false });
      }
    } else {
      slots.push({ token: ref.token, refIndexes: [i], isAlias: false, isGroup: isGroupRef(text, ref) });
    }
  });
  return slots;
}

/** 按每个泛称（按下标顺序）的指派结果，把白描替换成"带幼儿名"的版本。 */
export function applyChildNames(text: string, refs: PersonRef[], assignments: (string | undefined)[]): string {
  let out = text;
  // 从后往前替换，避免此前替换影响后续下标。
  for (let k = refs.length - 1; k >= 0; k--) {
    const name = assignments[k];
    const ref = refs[k];
    if (!name || !ref) continue;
    out = out.slice(0, ref.index) + name + out.slice(ref.index + ref.length);
  }
  return out;
}

/** 白描里出现的不同泛称（去重），用于提示老师场景有几人。 */
export function distinctPersonRefs(text: string): string[] {
  return Array.from(new Set(findPersonRefs(text).map((r) => r.token)));
}
