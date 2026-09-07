import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

import { ObservationReviewPage } from "./observation-review-page";

const mocks = vi.hoisted(() => ({ deleteMutate: vi.fn(), confirmMutate: vi.fn(), status: "ready_for_review" }));

const baseRecord = {
  id: 1,
  status: "ready_for_review",
  media: [],
  tags: [],
  child_id: null,
  area_name: "建构区",
  classroom_name: "中二班",
  child_name: null,
  narrative_source: "ai",
  purpose: "",
  narrative: "",
  analysis: "",
  strategy: "",
  ready_at: "2026-08-27T01:00:00Z",
  confirmed_at: null,
  observed_at: "2026-08-27T01:00:00Z",
  created_at: "2026-08-27T01:00:00Z",
  media_type: "image",
};

vi.mock("../features/observations/api", () => ({
  useObservation: vi.fn(() => ({ data: { ...baseRecord, status: mocks.status }, isLoading: false, isError: false, refetch: vi.fn() })),
  useObservationPeople: () => ({ data: undefined, isFetching: false, isError: false, refetch: vi.fn() }),
  useAssignObservationPeople: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useChildren: () => ({ data: [], isLoading: false, isError: false }),
  useIndicators: () => ({ data: [], isLoading: false, isError: false }),
  useGenerateNarrative: () => ({ data: undefined, isPending: false, isError: false, mutate: vi.fn(), mutateAsync: vi.fn() }),
  useUpdateObservation: () => ({ isPending: false, isError: false, mutate: vi.fn(), mutateAsync: vi.fn(), variables: undefined }),
  useSuggestTags: () => ({ data: undefined, isSuccess: false, isPending: false, isError: false, mutate: vi.fn() }),
  useSuggestAnalysis: () => ({ reset: vi.fn(), data: undefined, isPending: false, isError: false, mutate: vi.fn() }),
  useDecideTag: () => ({ isError: false, mutate: vi.fn() }),
  useAddTeacherTag: () => ({ isPending: false, isError: false, mutateAsync: vi.fn() }),
  useConfirmObservation: () => ({ isPending: false, isError: false, mutateAsync: mocks.confirmMutate }),
  useDeleteObservation: () => ({ isPending: false, mutate: mocks.deleteMutate }),
  useReplaceObservationChildren: () => ({ flush: vi.fn().mockResolvedValue(undefined), retry: vi.fn(), isPending: false, isError: false, mutate: vi.fn() }),
  getMediaFileUrl: (id: number) => `/api/media/${id}/file`,
  getMediaThumbnailUrl: (id: number) => `/api/media/${id}/thumbnail`,
}));

function renderReview() {
  return render(
    <MemoryRouter initialEntries={["/observations/1/review"]}>
      <Routes>
        <Route element={<ObservationReviewPage />} path="/observations/:observationId/review" />
      </Routes>
    </MemoryRouter>,
  );
}

describe("草稿删除", () => {
  beforeEach(() => {
    mocks.deleteMutate.mockReset();
    mocks.confirmMutate.mockReset();
  });

  it.each([
    ["ready_for_review", "草稿"],
    ["uploaded", "待整理素材"],
  ])("未完成草稿（%s）也能删除记录", (status) => {
    mocks.status = status;
    renderReview();

    const deleteButton = screen.getByRole("button", { name: "删除这条记录" });
    expect(deleteButton).toBeInTheDocument();

    fireEvent.click(deleteButton);
    expect(screen.getByRole("heading", { name: "删除这条记录？" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    expect(mocks.deleteMutate).toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });
});
