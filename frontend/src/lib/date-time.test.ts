import {
  compareTimestampsDescending,
  formatLocalTime,
  isLocalToday,
  parseApiTimestamp,
} from "./date-time";

describe("date-time", () => {
  it("parses an API UTC timestamp as one absolute instant", () => {
    expect(parseApiTimestamp("2026-08-23T12:34:32.426166Z").getTime())
      .toBe(Date.UTC(2026, 7, 23, 12, 34, 32, 426));
  });

  it("formats through the device local timezone", () => {
    const value = "2026-08-23T12:34:32Z";
    const expected = new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(value));
    expect(formatLocalTime(value)).toBe(expected);
  });

  it("uses the same local-date rule for today's list", () => {
    expect(isLocalToday(new Date().toISOString())).toBe(true);
    expect(compareTimestampsDescending(
      "2026-08-23T12:00:00Z",
      "2026-08-23T13:00:00Z",
    )).toBeGreaterThan(0);
  });
});
