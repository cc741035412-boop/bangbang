import type { Observation } from "../features/observations/api";
import { getKindergartenDateKey } from "./date-time";

export interface MonthSegment {
  /** 如 "1~10日" / "11~20日" / "21~30日" */
  label: string;
  records: Observation[];
}

/** 把一个月的素材按上旬/中旬/下旬（1~10、11~20、21~月末）分组。
 *  传入的 records 需已按"由近及远"（新→旧）排好；返回时按"贴近当下"的段优先：
 *  下旬 → 中旬 → 上旬，段内仍保持新→旧。 */
export function monthSegments(records: Observation[], year: number, month: number): MonthSegment[] {
  const lastDay = new Date(year, month, 0).getDate();
  const buckets: Record<number, Observation[]> = {};
  for (const record of records) {
    const dateKey = getKindergartenDateKey(record.created_at ?? record.observed_at);
    const day = Number(dateKey.slice(8, 10));
    const segment = day <= 10 ? 0 : day <= 20 ? 1 : 2;
    (buckets[segment] ??= []).push(record);
  }
  const starts = [1, 11, 21];
  const ends = [10, 20, lastDay];
  return [2, 1, 0]
    .filter((segment) => buckets[segment]?.length)
    .map((segment) => ({
      label: `${starts[segment]}~${ends[segment]}日`,
      records: buckets[segment] ?? [],
    }));
}
