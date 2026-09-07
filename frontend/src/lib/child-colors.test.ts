import { childAccent } from "./child-colors";

describe("child colors", () => {
  it("为不同 id 返回稳定的区分色（同 id 恒定）", () => {
    const a = childAccent(3);
    const b = childAccent(3);
    expect(a).toEqual(b);
    expect(a.bg).toBeTruthy();
    expect(a.text).toBeTruthy();
  });

  it("id 不同时颜色至少不完全重合于同一固定值", () => {
    const ids = new Set([0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((id) => childAccent(id).bg));
    // 合理分布：至少出现 3 种不同底色，避免所有幼儿同一色
    expect(ids.size).toBeGreaterThanOrEqual(4);
  });
});
