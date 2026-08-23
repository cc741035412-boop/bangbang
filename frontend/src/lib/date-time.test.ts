import {
  compareTimestampsDescending,
  formatKindergartenTime,
  isKindergartenToday,
  parseApiTimestamp,
} from "./date-time";

describe("date-time", () => {
  it("parses an API UTC timestamp as one absolute instant", () => {
    expect(parseApiTimestamp("2026-08-23T12:34:32.426166Z").getTime())
      .toBe(Date.UTC(2026, 7, 23, 12, 34, 32, 426));
  });

  it("always formats in the kindergarten's Beijing timezone", () => {
    expect(formatKindergartenTime("2026-08-23T14:18:00Z")).toBe("22:18");
  });

  it("uses the Beijing date boundary for today's list", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-23T16:00:00Z"));
    expect(isKindergartenToday("2026-08-23T16:30:00Z")).toBe(true);
    expect(isKindergartenToday("2026-08-23T15:30:00Z")).toBe(false);
    vi.useRealTimers();

    expect(compareTimestampsDescending(
      "2026-08-23T12:00:00Z",
      "2026-08-23T13:00:00Z",
    )).toBeGreaterThan(0);
  });
});
