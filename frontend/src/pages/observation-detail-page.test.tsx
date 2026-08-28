import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

import { ObservationDetailPage } from "./observation-detail-page";

const mocks = vi.hoisted(() => ({
  exportFile: vi.fn(),
}));

const record = {
  id: 12,
  child_id: 1,
  area_id: 1,
  classroom_id: 1,
  observer_id: 1,
  observed_at: "2026-08-27T01:40:00Z",
  age_group: "middle",
  status: "confirmed" as const,
  child_name: "幼儿A",
  classroom_name: "中一班",
  area_name: "建构区",
  child_confirmed_count: 2,
  children: [],
  observer: { id: 1, name: "教师A", classroom_id: 1 },
  media: [{
    id: 1,
    stored_filename: "sample.mp4",
    content_type: "video/mp4",
    size: 100,
    duration_sec: 204,
    uploaded_at: "2026-08-27T01:40:00Z",
  }],
  purpose: "观察搭建中的坚持",
  narrative: "幼儿A连续尝试搭建。",
  analysis: "教师填写的总体分析。",
  strategy: "下周继续提供连接材料。",
  tags: [
    { id: 1, observation_id: 12, indicator_code: "PHY-01", indicator_name: "持续参与活动", level: 2, source: "ai_suggested", accepted: true, confidence: 0.9, ai_reason: "连续尝试", created_at: "2026-08-27T01:40:00Z" },
    { id: 2, observation_id: 12, indicator_code: "SOC-01", indicator_name: "未采纳的指标", level: 1, source: "ai_suggested", accepted: false, created_at: "2026-08-27T01:40:00Z" },
  ],
};

vi.mock("../features/observations/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/observations/api")>();
  return {
    ...actual,
    useObservation: () => ({ data: record, isLoading: false, isError: false }),
    useIndicators: () => ({ data: [{ indicator_code: "PHY-01", dimension: "身体参与" }] }),
  };
});

vi.mock("../features/exports/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/exports/api")>();
  return { ...actual, fetchObservationExportAs: mocks.exportFile };
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/observations/12"]}>
      <Routes><Route path="observations/:observationId" element={<ObservationDetailPage />} /></Routes>
    </MemoryRouter>,
  );
}

describe("ObservationDetailPage", () => {
  beforeEach(() => {
    mocks.exportFile.mockReset();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:word") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  it("renders the complete draft with accepted indicators and one overall analysis", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "完整稿" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "幼儿A的观察记录" })).toBeInTheDocument();
    expect(screen.getByText("3 分 24 秒", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("1. 持续参与活动")).toBeInTheDocument();
    expect(screen.getByText("身体参与")).toBeInTheDocument();
    expect(screen.queryByText("未采纳的指标")).not.toBeInTheDocument();
    expect(screen.getAllByText("教师填写的总体分析。")).toHaveLength(1);
  });

  it("downloads the real Word response and then shows the success and share states", async () => {
    const blob = new Blob(["word-content"], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    mocks.exportFile.mockResolvedValue({ blob, fileName: "幼儿A_观察记录_20260827.docx", format: "docx", size: blob.size });
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "导出" }));
    expect(screen.getByRole("dialog", { name: "导出格式" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /PDF/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Markdown/ })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "确认导出" }));

    expect(await screen.findByText("导出成功！")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "幼儿A_观察记录_20260827.docx" })).toBeInTheDocument();
    expect(mocks.exportFile).toHaveBeenCalledWith(12, "docx", true);

    fireEvent.click(screen.getByRole("button", { name: "分享导出的 Word 文档" }));
    expect(screen.getByRole("dialog", { name: "分享文件" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "系统分享" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "再次下载" })).toBeEnabled();
  });

  it("keeps the export sheet open and explains a failed export", async () => {
    mocks.exportFile.mockRejectedValue(new Error("Word 文档暂时没有导出成功"));
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "导出" }));
    fireEvent.click(screen.getByRole("button", { name: "确认导出" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Word 文档暂时没有导出成功");
    await waitFor(() => expect(screen.getByRole("dialog", { name: "导出格式" })).toBeInTheDocument());
    expect(screen.queryByText("导出成功！")).not.toBeInTheDocument();
  });

  it("exports the format selected by the teacher", async () => {
    const blob = new Blob(["pdf-content"], { type: "application/pdf" });
    mocks.exportFile.mockResolvedValue({
      blob,
      fileName: "幼儿A_观察记录_20260827.pdf",
      format: "pdf",
      size: blob.size,
    });
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "导出" }));
    fireEvent.click(screen.getByRole("button", { name: /PDF/ }));
    fireEvent.click(screen.getByRole("button", { name: "确认导出" }));

    expect(await screen.findByText("导出成功！")).toBeInTheDocument();
    expect(mocks.exportFile).toHaveBeenCalledWith(12, "pdf", true);
  });
});
