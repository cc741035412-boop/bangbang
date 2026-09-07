import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { MinePage } from "./mine-page";
import { MonthMediaPage } from "./month-media-page";
import { TodayMediaPage } from "./today-media-page";

const records = [
  { id: 1, area_id: 1, child_id: 1, observed_at: "2026-08-27T01:00:00Z", created_at: "2026-08-27T01:00:00Z", age_group: "middle", media_type: "video", status: "confirmed" as const },
  { id: 2, area_id: 2, child_id: 1, observed_at: "2026-08-26T01:00:00Z", created_at: "2026-08-26T01:00:00Z", age_group: "middle", media_type: "image", status: "ready_for_review" as const },
];

const query = <T,>(data: T) => ({ data, isLoading: false, isError: false, refetch: vi.fn() });

vi.mock("../features/observations/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/observations/api")>();
  return {
    ...actual,
    useTodayMediaData: () => ({
      observations: query(records),
      areas: query([{ id: 1, code: "blocks", name: "建构区" }, { id: 2, code: "role", name: "角色区" }]),
      children: query([{ id: 1, name: "幼儿A", classroom_id: 1 }]),
      media: query([]),
    }),
  };
});

vi.mock("../features/settings/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/settings/api")>();
  return {
    ...actual,
    useSettingsData: () => ({
      children: query([{ id: 1, name: "幼儿A", classroom_id: 1, birth_date: null, gender: null }]),
      teachers: query([{ id: 1, name: "教师A", classroom_id: 1 }]),
    }),
  };
});

vi.mock("../features/auth/auth-context-value", () => ({
  useAuth: () => ({
    account: {
      phone: "13800000001",
      name: "教师A",
      kindergarten_name: "测试幼儿园A",
      classroom_name: "中一班",
    },
    enabled: true,
    isLoading: false,
  }),
}));

vi.mock("../features/auth/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/auth/api")>();
  return {
    ...actual,
    useLogout: () => ({ isPending: false, mutate: vi.fn() }),
  };
});

describe("home pages", () => {
  beforeAll(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-27T01:00:00Z"));
  });

  afterAll(() => vi.useRealTimers());

  it("shows only today's material on the today tab", () => {
    render(<MemoryRouter><TodayMediaPage /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "打开建构区记录" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "打开角色区记录" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "今日素材" })).toHaveAttribute("aria-current", "page");
  });

  it("groups all current-month materials into 旬 segments, 由近及远", () => {
    render(<MemoryRouter><MonthMediaPage /></MemoryRouter>);
    // 8/27、8/26 都在下旬（21~31日），显示为一个 segment 标题
    expect(screen.getByRole("heading", { name: "21~31日 · 2 条" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开建构区记录" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开角色区记录" })).toBeInTheDocument();
    // 右上角有月份选择交互键
    expect(screen.getByRole("button", { name: "选择月份" })).toBeInTheDocument();
  });

  it("can switch month via the picker", () => {
    render(<MemoryRouter><MonthMediaPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "选择月份" }));
    fireEvent.click(screen.getByRole("button", { name: "9月" }));
    // mock 数据只有 8 月，切到 9 月应显示空态
    expect(screen.getByText("9月还没有素材")).toBeInTheDocument();
  });

  it("derives child and monthly record counts from confirmed observations", () => {
    render(<MemoryRouter><MinePage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "教师A" })).toBeInTheDocument();
    expect(screen.getByText("1 条")).toBeInTheDocument();
    expect(screen.getByText("1 篇")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /导出本月 Word/ })).toHaveAttribute("href", expect.stringContaining("/api/exports/monthly"));
  });
});
