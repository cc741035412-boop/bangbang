import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router";

import { AppRoutes } from "./routes";

const mocks = vi.hoisted(() => ({ mutate: vi.fn(), reset: vi.fn() }));

vi.mock("../pages/observation-review-page", () => ({
  ObservationReviewPage: function ReviewDestination() {
    const location = useLocation();
    return <output aria-label="草稿地址">{location.pathname}{location.search}</output>;
  },
}));

function query<T>(data: T) {
  return { data, isLoading: false, isError: false, refetch: vi.fn() };
}

vi.mock("../features/auth/auth-context-value", () => ({
  useAuth: () => ({
    account: {
      id: 1,
      phone: "13800000001",
      teacher_id: 1,
      name: "教师A",
      kindergarten_id: 1,
      kindergarten_name: "测试幼儿园A",
      classroom_id: 1,
      classroom_name: "中一班",
      created_at: "2026-08-27T00:00:00Z",
    },
    enabled: true,
    isLoading: false,
  }),
}));

vi.mock("../features/observations/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/observations/api")>();
  return {
    ...actual,
    useTodayMediaData: () => ({
      observations: query([]),
      areas: query([{ id: 1, code: "blocks", name: "建构区" }]),
      children: query([]),
      media: query([]),
    }),
    useAreas: () => query([{ id: 1, code: "blocks", name: "建构区" }]),
    useSubmitCapture: () => ({
      mutate: mocks.mutate,
      reset: mocks.reset,
      isPending: false,
      isError: false,
      error: null,
    }),
  };
});

function renderAt(path = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("端到端流程（今日素材 → 上传素材）", () => {
  beforeEach(() => {
    mocks.mutate.mockReset();
    mocks.reset.mockReset();
  });

  it("进入今日素材页，打开上传底页，选区域+照片后提交", () => {
    renderAt("/");

    expect(screen.getByRole("heading", { name: "今日素材" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "上传素材" }));

    // 上传底页：先选文件 + 区域才能提交
    const submit = screen.getByRole("button", { name: "上传并继续" });
    expect(submit).toBeDisabled();

    const file = new File(["image"], "photo.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("照片"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("radio", { name: "建构区" }));

    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    expect(mocks.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ areaId: 1, file }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("手机端结构：移动容器、主 tab 与安全底边都在（375/390 通用结构）", () => {
    renderAt("/");
    // MobilePage 用 max-w-[430px] 的移动容器承载
    expect(document.querySelector(".max-w-\\[430px\\]")).toBeInTheDocument();
    // 主导航
    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "今日素材" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "本月素材" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "我的" })).toBeInTheDocument();
    // nav 的 safe-bottom（safe-area-inset）工具类存在，避免 iPhone 底部被遮挡
    expect(screen.getByRole("navigation", { name: "主导航" }).className).toContain("safe-bottom");
  });

  it("上传成功直接进入对应草稿，准备选择幼儿和观察目标", () => {
    mocks.mutate.mockImplementation((_input, callbacks) => callbacks.onSuccess({ observationId: 42 }));
    renderAt("/?upload=1");
    fireEvent.change(screen.getByLabelText("照片"), {
      target: { files: [new File(["image"], "photo.png", { type: "image/png" })] },
    });
    fireEvent.click(screen.getByRole("radio", { name: "建构区" }));
    fireEvent.click(screen.getByRole("button", { name: "上传并继续" }));
    expect(screen.getByLabelText("草稿地址")).toHaveTextContent("/observations/42/review");
    expect(screen.queryByRole("heading", { name: "今日素材" })).not.toBeInTheDocument();
  });
});
