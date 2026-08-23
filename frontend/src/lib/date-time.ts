const LOCAL_TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const LOCAL_DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  month: "long",
  day: "numeric",
  weekday: "long",
});

export function parseApiTimestamp(value: string) {
  return new Date(value);
}

export function formatLocalTime(value: string) {
  return LOCAL_TIME_FORMATTER.format(parseApiTimestamp(value));
}

export function formatLocalToday() {
  return LOCAL_DATE_FORMATTER.format(new Date());
}

export function isLocalToday(value?: string | null) {
  if (!value) return false;
  const date = parseApiTimestamp(value);
  const today = new Date();
  return date.getFullYear() === today.getFullYear()
    && date.getMonth() === today.getMonth()
    && date.getDate() === today.getDate();
}

export function compareTimestampsDescending(a?: string | null, b?: string | null) {
  return Date.parse(b ?? "") - Date.parse(a ?? "");
}
