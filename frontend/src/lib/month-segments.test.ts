import { monthSegments } from "./month-segments";
import type { Observation } from "../features/observations/api";

function obs(day: number, id: number): Observation {
  return {
    id,
    area_id: 1,
    child_id: null,
    observed_at: `2026-09-${String(day).padStart(2, "0")}T01:00:00Z`,
    created_at: `2026-09-${String(day).padStart(2, "0")}T01:00:00Z`,
    age_group: "middle",
    media_type: "image",
    status: "confirmed" as const,
  };
}

describe("month segments", () => {
  it("按上/中/下旬分组，且贴近当下的段在前（由近及远）", () => {
    const records = [obs(3, 1), obs(12, 2), obs(25, 3), obs(15, 4), obs(30, 5)];
    const groups = monthSegments(records, 2026, 9);
    expect(groups.map((g) => g.label)).toEqual(["21~30日", "11~20日", "1~10日"]);
    expect(groups[0]?.records.map((r) => r.id)).toEqual([3, 5]); // 25, 30
    expect(groups[1]?.records.map((r) => r.id)).toEqual([2, 4]); // 12, 15
    expect(groups[2]?.records.map((r) => r.id)).toEqual([1]); // 3
  });

  it("空月份返回空数组", () => {
    expect(monthSegments([], 2026, 9)).toEqual([]);
  });

  it("月底段结束于当月实际天数", () => {
    expect(monthSegments([obs(28, 1)], 2026, 2)[0]?.label).toBe("21~28日"); // 2026-02 = 28 天
    expect(monthSegments([obs(29, 1)], 2024, 2)[0]?.label).toBe("21~29日"); // 2024 闰 2 月
    expect(monthSegments([obs(30, 1)], 2026, 9)[0]?.label).toBe("21~30日"); // 2026-09 = 30 天
  });
});
