import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";

import { ObservationReviewPage } from "./observation-review-page";

const mocks = vi.hoisted(() => ({
  replaceChildren: vi.fn(),
  childPending: false,
  selectedIds: undefined as number[] | undefined,
  updateObservation: vi.fn(),
  deleteMutate: vi.fn(),
  confirmMutate: vi.fn(),
  judgment: false,
  childrenEmpty: false,
  childrenError: false,
  refetchChildren: vi.fn(),
  status: "ready_for_review",
  generateNarrative: vi.fn(),
  generationError: false,
  suggestTags: vi.fn(),
}));

const record = {
  id: 1,
  status: "ready_for_review",
  media: [],
  tags: [],
  child_id: 3,
  children: [{ id: 3, name: "王馨瑶", classroom_id: 2, is_primary: true, confirmed_observation_count: 0 }],
  area_name: "建构区",
  classroom_name: "大二班",
  child_name: "王馨瑶",
  narrative_source: "ai",
  purpose: "",
  narrative: "约2.1秒时，幼儿A（扎马尾）从右侧入镜。约6.2秒时，幼儿A背向镜头。",
  analysis: "",
  strategy: "",
  ready_at: "2026-08-27T01:00:00Z",
  confirmed_at: null,
  observed_at: "2026-08-27T01:00:00Z",
  created_at: "2026-08-27T01:00:00Z",
  media_type: "image",
};

vi.mock("../features/observations/api", () => ({
  useObservation: vi.fn(() => ({ data: { ...record, status: mocks.status, ...(mocks.judgment ? { purpose: "观察材料选择", suggestions_ready: true, tags: [{ id: 8, indicator_code: "4.4", indicator_name: "问题解决", level: 1, source: "ai_suggested", accepted: true }] } : {}) }, isLoading: false, isError: false, refetch: vi.fn() })),
  useObservationPeople: () => ({ data: undefined, isFetching: false, isError: false, refetch: vi.fn() }),
  useAssignObservationPeople: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useChildren: () => ({
    data: mocks.childrenEmpty ? [] : [
      { id: 3, name: "王馨瑶", classroom_id: 2 },
      { id: 4, name: "李金悦", classroom_id: 2 },
    ],
    isLoading: false,
    isError: mocks.childrenError,
    refetch: mocks.refetchChildren,
  }),
  useIndicators: () => ({
    data: [
      { dimension: "身体参与", indicator_name: "身体行为参与度" },
      { dimension: "社会互动", indicator_name: "互动方式" },
    ],
    isLoading: false,
    isError: false,
  }),
  useGenerateNarrative: () => ({ data: undefined, isPending: false, isError: mocks.generationError, mutate: mocks.generateNarrative, mutateAsync: mocks.generateNarrative }),
  useUpdateObservation: () => ({ isPending: false, isError: false, mutate: mocks.updateObservation, mutateAsync: mocks.updateObservation, variables: undefined }),
  useSuggestTags: () => ({ data: undefined, isSuccess: false, isPending: false, isError: false, mutate: mocks.suggestTags, mutateAsync: mocks.suggestTags }),
  useSuggestAnalysis: () => ({ reset: vi.fn(), data: undefined, isPending: false, isError: false, mutate: vi.fn() }),
  useDecideTag: () => ({ isError: false, mutate: vi.fn() }),
  useAddTeacherTag: () => ({ isPending: false, isError: false, mutateAsync: vi.fn() }),
  useConfirmObservation: () => ({ isPending: false, isError: false, mutateAsync: mocks.confirmMutate }),
  useDeleteObservation: () => ({ isPending: false, mutate: mocks.deleteMutate }),
  useReplaceObservationChildren: () => ({ flush: vi.fn().mockResolvedValue(undefined), retry: vi.fn(), selectedIds: mocks.selectedIds, isPending: mocks.childPending, isError: false, mutate: mocks.replaceChildren }),
  getMediaFileUrl: (id: number) => `/api/media/${id}/file`,
  getMediaThumbnailUrl: (id: number) => `/api/media/${id}/thumbnail`,
}));

function renderReview(path = "/observations/1/review") {
  return render(
    <StrictMode><MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<ObservationReviewPage />} path="/observations/:observationId/review" />
      </Routes>
    </MemoryRouter></StrictMode>,
  );
}

describe("观察对象（多选 + 自动带入）", () => {
  beforeEach(() => {
    mocks.replaceChildren.mockReset();
    mocks.childPending = false;
    mocks.selectedIds = undefined;
    mocks.updateObservation.mockReset();
    mocks.confirmMutate.mockReset();
    mocks.judgment = false;
    mocks.childrenEmpty = false;
    mocks.childrenError = false;
    mocks.refetchChildren.mockReset();
    mocks.status = "ready_for_review";
    mocks.generateNarrative.mockReset();
    mocks.generationError = false;
    mocks.suggestTags.mockReset();
    vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  });

  it("采用指标后进入必填分析策略，缺任何一项都不能确认", async () => {
    mocks.judgment = true;
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: "核对好了，推荐指标" }));
    fireEvent.click(await screen.findByRole("button", { name: "下一步：填写分析和策略" }));
    const confirm = screen.getByRole("button", { name: "确认记录，查看报告" });
    expect(confirm).toBeDisabled();
    expect(screen.getByLabelText("我的分析")).toBeRequired();
    expect(screen.getByLabelText("下一步支持策略")).toBeRequired();
    fireEvent.change(screen.getByLabelText("我的分析"), { target: { value: "调整底座后继续搭建" } });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText("下一步支持策略"), { target: { value: "提供不同底板继续观察" } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(mocks.confirmMutate).toHaveBeenCalledOnce());
  });

  it("新上传的草稿先准备信息，即使旧 URL 带自动生成标记也不调用 AI", () => {
    mocks.status = "uploaded";
    renderReview("/observations/1/review?generate=1");
    expect(mocks.generateNarrative).not.toHaveBeenCalled();
  });

  it.each(["processing", "ready_for_review", "confirmed"])("%s 的记录不因上传标记再次生成", (status) => {
    mocks.status = status;
    renderReview("/observations/1/review?generate=1");
    expect(mocks.generateNarrative).not.toHaveBeenCalled();
  });

  it("选择目标后先保存，再自动生成；无目标的主按钮不可用", async () => {
    mocks.status = "uploaded";
    renderReview();
    const button = screen.getByRole("button", { name: "按当前目标重新生成白描" });
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "观察幼儿如何选用与组合材料" }));
    fireEvent.click(button);
    await waitFor(() => expect(mocks.generateNarrative).toHaveBeenCalledWith("focused"));
    expect(mocks.updateObservation).toHaveBeenCalledWith(expect.objectContaining({ purpose: "观察幼儿如何选用与组合材料" }));
    expect(mocks.updateObservation.mock.invocationCallOrder[0] ?? 0).toBeLessThan(mocks.generateNarrative.mock.invocationCallOrder[0] ?? 0);
  });

  it("先看看素材不要求目标，也会先保存观察对象提示", async () => {
    mocks.status = "uploaded";
    renderReview();
    fireEvent.change(screen.getByLabelText("画面中是哪位幼儿？（选填）"), { target: { value: "左侧红衣幼儿" } });
    fireEvent.click(screen.getByRole("button", { name: "先看看素材" }));
    await waitFor(() => expect(mocks.generateNarrative).toHaveBeenCalledWith("explore"));
    expect(mocks.updateObservation).toHaveBeenCalledWith(expect.objectContaining({ purpose: "", note: "左侧红衣幼儿" }));
  });

  it("保存失败不调用 AI，并保留重试入口", async () => {
    mocks.status = "failed";
    mocks.updateObservation.mockRejectedValueOnce(new Error("offline"));
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: "先看看素材" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(mocks.generateNarrative).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "先看看素材" }));
    await waitFor(() => expect(mocks.generateNarrative).toHaveBeenCalledWith("explore"));
  });

  it("当前班级没有幼儿时显示原因和添加入口", () => {
    mocks.childrenEmpty = true;
    renderReview();
    expect(screen.getByText("当前班级还没有幼儿名单，添加后即可选择观察对象。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "添加幼儿" })).toHaveAttribute("href", "/children");
  });

  it("幼儿名单加载失败可以重试，不误报班级为空", () => {
    mocks.childrenEmpty = true;
    mocks.childrenError = true;
    renderReview();
    expect(screen.queryByRole("link", { name: "添加幼儿" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    expect(mocks.refetchChildren).toHaveBeenCalledOnce();
  });

  it("不会仅凭名单把画面中的幼儿A自动认作某个姓名", () => {
    renderReview();
    expect(screen.getByText(/幼儿A（扎马尾）/)).toBeInTheDocument();
  });

  it("点击另一个主观察幼儿直接切换主体，原主体保留为其他幼儿", () => {
    renderReview();
    const liButton = screen.getByRole("radio", { name: "李金悦" });
    fireEvent.click(liButton);
    expect(mocks.replaceChildren).toHaveBeenCalledWith([4, 3]);
  });

  it("保存中仍可切换主体，显示最新角色而非服务器旧记录", () => {
    mocks.childPending = true;
    mocks.selectedIds = [4, 3];
    renderReview();
    const primary = screen.getByRole("radio", { name: "李金悦" });
    const other = screen.getByRole("checkbox", { name: "王馨瑶" });
    expect(primary).toHaveAttribute("aria-checked", "true");
    expect(other).toHaveAttribute("aria-checked", "true");
    expect(primary).toBeEnabled();
    expect(other).toBeEnabled();
    fireEvent.click(screen.getByRole("radio", { name: "王馨瑶" }));
    expect(mocks.replaceChildren).toHaveBeenCalledWith([3, 4]);
    expect(screen.getByRole("button", { name: "核对好了，推荐指标" })).toBeDisabled();
  });

  it("目标可多选、取消，也可添加自定义目标后用于推荐", async () => {
    renderReview();
    const first = screen.getByRole("button", { name: "观察幼儿如何选用与组合材料" });
    const second = screen.getByRole("button", { name: "观察遇到困难后如何尝试和调整" });
    fireEvent.click(first);
    fireEvent.click(second);
    expect(screen.getByText("已选 2 个")).toBeInTheDocument();
    fireEvent.click(first);
    expect(first).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: "添加观察目标" }));
    fireEvent.change(screen.getByLabelText("新的观察目标"), { target: { value: "观察如何调整底座" } });
    fireEvent.click(screen.getByRole("button", { name: "添加并选中" }));
    expect(screen.getByRole("button", { name: "观察如何调整底座" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "核对好了，推荐指标" }));
    await waitFor(() => expect(mocks.suggestTags).toHaveBeenCalledOnce());
    expect(mocks.updateObservation).toHaveBeenCalledWith(expect.objectContaining({ purpose: "观察遇到困难后如何尝试和调整\n观察如何调整底座" }));
  });
});
