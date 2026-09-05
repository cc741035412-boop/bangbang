// 观察记录表达的是幼儿园当地发生时间，不是查看设备所在地时间。
// 产品固定服务深圳园所，因此所有展示和“今日”判断统一使用北京时间。
export const KINDERGARTEN_TIME_ZONE = "Asia/Shanghai";

const KINDERGARTEN_TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: KINDERGARTEN_TIME_ZONE,
});

const KINDERGARTEN_DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  month: "long",
  day: "numeric",
  weekday: "long",
  timeZone: KINDERGARTEN_TIME_ZONE,
});

const KINDERGARTEN_PLAIN_DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  month: "long",
  day: "numeric",
  timeZone: KINDERGARTEN_TIME_ZONE,
});

const KINDERGARTEN_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: KINDERGARTEN_TIME_ZONE,
});

const KINDERGARTEN_DATE_KEY_FORMATTER = new Intl.DateTimeFormat("en-CA", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  timeZone: KINDERGARTEN_TIME_ZONE,
});

const KINDERGARTEN_YEAR_MONTH_FORMATTER = new Intl.DateTimeFormat("en-CA", {
  year: "numeric",
  month: "2-digit",
  timeZone: KINDERGARTEN_TIME_ZONE,
});

export function parseApiTimestamp(value: string) {
  return new Date(value);
}

export function formatKindergartenTime(value: string) {
  return KINDERGARTEN_TIME_FORMATTER.format(parseApiTimestamp(value));
}

export function formatKindergartenDateTime(value: string) {
  return KINDERGARTEN_DATE_TIME_FORMATTER.format(parseApiTimestamp(value));
}

export function formatKindergartenToday() {
  return KINDERGARTEN_DATE_FORMATTER.format(new Date());
}

export function isKindergartenToday(value?: string | null) {
  if (!value) return false;
  return getKindergartenDateKey(value) === getKindergartenDateKey(new Date());
}

export function formatKindergartenDate(value: string) {
  return KINDERGARTEN_PLAIN_DATE_FORMATTER.format(parseApiTimestamp(value));
}

export function getKindergartenDateKey(value: string | Date) {
  const parts = KINDERGARTEN_DATE_KEY_FORMATTER.formatToParts(typeof value === "string" ? parseApiTimestamp(value) : value);
  const year = parts.find((part) => part.type === "year")?.value ?? "";
  const month = parts.find((part) => part.type === "month")?.value ?? "";
  const day = parts.find((part) => part.type === "day")?.value ?? "";
  return `${year}-${month}-${day}`;
}

export function isKindergartenYearMonth(value: string | null | undefined, year: number, month: number) {
  if (!value) return false;
  return getKindergartenDateKey(value).startsWith(`${year}-${String(month).padStart(2, "0")}-`);
}

export function compareTimestampsDescending(a?: string | null, b?: string | null) {
  return Date.parse(b ?? "") - Date.parse(a ?? "");
}

export function getKindergartenYearMonth(value = new Date()) {
  const parts = KINDERGARTEN_YEAR_MONTH_FORMATTER.formatToParts(value);
  return {
    year: Number(parts.find((part) => part.type === "year")?.value),
    month: Number(parts.find((part) => part.type === "month")?.value),
  };
}

/** 今天的幼儿园本地日期键，如 "2026-08-27"（用于检索页的“今天/本月”快捷区间）。 */
export function getKindergartenTodayKey() {
  return getKindergartenDateKey(new Date());
}

/** 由日期键推本月第一天："2026-08-27" → "2026-08-01"。 */
export function kindergartenMonthStartKey(dateKey: string) {
  return `${dateKey.slice(0, 7)}-01`;
}
