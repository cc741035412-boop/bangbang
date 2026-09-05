import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import {
  useAllMedia,
  useAreas,
  useChildren,
  useObservationSearch,
} from "../features/observations/api";
import { RecordSearchPage } from "./record-search-page";

const query = <T,>(data: T) => ({
  data,
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
});

const records = [
  {
    id: 1,
    area_id: 1,
    child_id: 1,
    observed_at: "2026-08-27T01:00:00Z",
    age_group: "middle",
    media_type: "video",
    status: "confirmed" as const,
  },
  {
    id: 2,
    area_id: 2,
    child_id: 1,
    observed_at: "2026-08-26T01:00:00Z",
    age_group: "middle",
    media_type: "image",
    status: "ready_for_review" as const,
  },
];

vi.mock("../features/observations/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/observations/api")>();
  return {
    ...actual,
    useObservationSearch: vi.fn(),
    useAreas: vi.fn(),
    useChildren: vi.fn(),
    useAllMedia: vi.fn(),
  };
});

describe("record search page", () => {
  beforeAll(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-27T01:00:00Z"));
  });

  afterAll(() => vi.useRealTimers());

  beforeEach(() => {
    vi.mocked(useObservationSearch).mockReturnValue(query(records));
    vi.mocked(useAreas).mockReturnValue(query([
      { id: 1, code: "blocks", name: "建构区" },
      { id: 2, code: "role", name: "角色区" },
    ]));
    vi.mocked(useChildren).mockReturnValue(query([
      { id: 1, name: "幼儿A", classroom_id: 1 },
    ]));
    vi.mocked(useAllMedia).mockReturnValue(query([]));
  });

  it("lists the records returned by the current filters and groups by date", () => {
    render(<MemoryRouter><RecordSearchPage /></MemoryRouter>);
    expect(screen.getByText("共 2 条记录 · 最新的在最上面")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开建构区记录" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开角色区记录" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "8月27日 · 今天" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "8月26日" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "幼儿" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "游戏区域" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "状态" })).toBeInTheDocument();
    // 默认"全部时间"，不会出现自定义起止输入
    expect(screen.queryByLabelText("起始日期")).not.toBeInTheDocument();
  });

  it("offers only the four status buckets the teacher cares about", () => {
    render(<MemoryRouter><RecordSearchPage /></MemoryRouter>);
    const combo = screen.getByRole("combobox", { name: "状态" });
    const labels = within(combo).getAllByRole("option").map((option) => option.textContent);
    expect(labels).toEqual(["全部状态", "草稿状态", "待生成状态", "已生成状态"]);
  });

  it("applies the today shortcut as a single-day range", () => {
    render(<MemoryRouter><RecordSearchPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "本日" }));
    const lastCall = vi.mocked(useObservationSearch).mock.calls.at(-1);
    expect(lastCall?.[0]).toEqual({
      child_id: undefined,
      area_id: undefined,
      status: undefined,
      date_from: "2026-08-27",
      date_to: "2026-08-27",
    });
  });

  it("applies the month shortcut from month start to today", () => {
    render(<MemoryRouter><RecordSearchPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "本月" }));
    const lastCall = vi.mocked(useObservationSearch).mock.calls.at(-1);
    expect(lastCall?.[0]).toEqual({
      child_id: undefined,
      area_id: undefined,
      status: undefined,
      date_from: "2026-08-01",
      date_to: "2026-08-27",
    });
  });

  it("picks a single day by choosing only one of the custom date fields", () => {
    render(<MemoryRouter><RecordSearchPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "自定义日期" }));
    fireEvent.change(screen.getByLabelText("截止日期"), { target: { value: "2026-08-15" } });
    const lastCall = vi.mocked(useObservationSearch).mock.calls.at(-1);
    expect(lastCall?.[0]).toEqual({
      child_id: undefined,
      area_id: undefined,
      status: undefined,
      date_from: "2026-08-15",
      date_to: "2026-08-15",
    });
  });

  it("supports an arbitrary date range from previous month to this month", () => {
    render(<MemoryRouter><RecordSearchPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "自定义日期" }));
    fireEvent.change(screen.getByLabelText("起始日期"), { target: { value: "2026-07-15" } });
    fireEvent.change(screen.getByLabelText("截止日期"), { target: { value: "2026-08-15" } });
    const lastCall = vi.mocked(useObservationSearch).mock.calls.at(-1);
    expect(lastCall?.[0]).toEqual({
      child_id: undefined,
      area_id: undefined,
      status: undefined,
      date_from: "2026-07-15",
      date_to: "2026-08-15",
    });
  });

  it("ignores an inverted custom range and warns instead", () => {
    render(<MemoryRouter><RecordSearchPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "自定义日期" }));
    fireEvent.change(screen.getByLabelText("起始日期"), { target: { value: "2026-08-15" } });
    fireEvent.change(screen.getByLabelText("截止日期"), { target: { value: "2026-08-10" } });
    const lastCall = vi.mocked(useObservationSearch).mock.calls.at(-1);
    expect(lastCall?.[0]).toEqual({
      child_id: undefined,
      area_id: undefined,
      status: undefined,
      date_from: undefined,
      date_to: undefined,
    });
    expect(screen.getByText(/开始日期不能晚于结束日期/)).toBeInTheDocument();
  });

  it("shows an empty state when nothing matches", () => {
    vi.mocked(useObservationSearch).mockReturnValue(query([]));
    render(<MemoryRouter><RecordSearchPage /></MemoryRouter>);
    expect(screen.getByText("没有找到符合条件的记录")).toBeInTheDocument();
  });
});
