import { describe, expect, it } from "vitest";

import { applyChildNames, distinctPersonRefs, findPersonRefs, isGroupRef, isGroupToken } from "./substitute-children";

describe("substitute-children", () => {
  const text = "左侧女童手握黄色捞网；中间男童低头；右侧女童在一旁。幼儿在旁观看。";

  it("识别白描里的人物泛称（不重复、不重叠）", () => {
    const refs = findPersonRefs(text);
    const tokens = refs.map((r) => r.token);
    // 女童、男童、女童、幼儿
    expect(tokens).toEqual(["女童", "男童", "女童", "幼儿"]);
    expect(refs.map((r) => r.index)).toEqual(
      [text.indexOf("女童"), text.indexOf("男童"), text.indexOf("女童", 5), text.indexOf("幼儿")]
    );
  });

  it("逐个把泛称代入幼儿名", () => {
    const refs = findPersonRefs(text);
    const out = applyChildNames(text, refs, ["李金悦", "高兴", "刘安澜", "李金悦"]);
    expect(out).toContain("左侧李金悦手握黄色捞网");
    expect(out).toContain("中间高兴低头");
    expect(out).toContain("右侧刘安澜在一旁");
    expect(out).toContain("李金悦在旁观看");
    expect(out).not.toContain("女童");
    expect(out).not.toContain("男童");
  });

  it("未指认的泛称保持不变", () => {
    const refs = findPersonRefs(text);
    const out = applyChildNames(text, refs, ["李金悦", undefined, undefined, "李金悦"]);
    expect(out).toContain("左侧李金悦");
    expect(out).toContain("中间男童");
    expect(out).toContain("右侧女童");
  });

  it("distinctPersonRefs 去重", () => {
    expect(distinctPersonRefs(text)).toEqual(["女童", "男童", "幼儿"]);
  });

  it("识别群体泛称", () => {
    expect(isGroupToken("孩子们")).toBe(true);
    expect(isGroupToken("小朋友们")).toBe(true);
    expect(isGroupToken("幼儿们")).toBe(true);
    expect(isGroupToken("女孩")).toBe(false);
    expect(isGroupToken("男童")).toBe(false);
    expect(isGroupToken("幼儿")).toBe(false);
  });

  it("群体泛称不参与代入（留空即跳过）", () => {
    const t = "孩子们在沙池玩，女孩在旁观看。";
    const refs = findPersonRefs(t);
    // 群体"孩子们"留空 → 保持原词；"女孩"代入名字
    const out = applyChildNames(t, refs, ["", "李金悦"]);
    expect(out).toContain("孩子们在沙池玩");
    expect(out).toContain("李金悦在旁观看");
    expect(out).toContain("孩子们");
    expect(out).not.toContain("女孩");
  });

  it("带数量词的群体泛称也能识别为群体", () => {
    const groupCases = [
      "几名孩子在搭积木。",
      "一群孩子在沙池玩。",
      "三四个孩子围过来看。",
      "两名幼儿蹲在地上。",
      "好几个孩子跑开了。",
      "许多孩子都在活动。",
      "所有的孩子都在玩。",
      "这些孩子在玩游戏。",
      "一些孩子坐在地上。",
      "更多孩子涌了进来。",
      "一堆孩子围在边上。",
      "好些孩子跟着跑。",
      "大批孩子挤过来。",
    ];
    for (const t of groupCases) {
      const ref = findPersonRefs(t)[0];
      expect(isGroupRef(t, ref), t).toBe(true);
    }
  });

  it("单数/序数的泛称不应判为群体", () => {
    const singularCases = [
      "一个孩子蹲在地上。",
      "一名幼儿走过来。",
      "第三个孩子站起来。",
      "每位孩子都拿到玩具。",
      "这边孩子在看什么。",
      "孩子独自在玩。",
    ];
    for (const t of singularCases) {
      const ref = findPersonRefs(t)[0];
      expect(isGroupRef(t, ref), t).toBe(false);
    }
  });

  it("带穿着/性别的个体不算群体，群体词才算（防误判回归）", () => {
    const t = "先有几名孩子在沙地，戴黑帽穿白上衣黄雨靴的男孩蹲着，旁边穿浅蓝上衣的男孩，最后，一群孩子跑过来，穿绿条纹上衣的女孩在看。";
    const refs = findPersonRefs(t);
    // 按出现顺序：先有几名孩子(群体)、白上衣男孩(个体)、浅蓝上衣男孩(个体)、一群孩子(群体)、绿条纹女孩(个体)
    const expected = [true, false, false, true, false];
    expect(refs.length).toBe(expected.length);
    refs.forEach((r, i) => expect(isGroupRef(t, r), `第${i}处「${r.token}」`).toBe(expected[i]));
  });
});
