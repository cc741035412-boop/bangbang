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

const KINDERGARTEN_DATE_KEY_FORMATTER = new Intl.DateTimeFormat("en-CA", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  timeZone: KINDERGARTEN_TIME_ZONE,
});

export function parseApiTimestamp(value: string) {
  return new Date(value);
}

export function formatKindergartenTime(value: string) {
  return KINDERGARTEN_TIME_FORMATTER.format(parseApiTimestamp(value));
}

export function formatKindergartenToday() {
  return KINDERGARTEN_DATE_FORMATTER.format(new Date());
}

export function isKindergartenToday(value?: string | null) {
  if (!value) return false;
  return KINDERGARTEN_DATE_KEY_FORMATTER.format(parseApiTimestamp(value))
    === KINDERGARTEN_DATE_KEY_FORMATTER.format(new Date());
}

export function compareTimestampsDescending(a?: string | null, b?: string | null) {
  return Date.parse(b ?? "") - Date.parse(a ?? "");
}
