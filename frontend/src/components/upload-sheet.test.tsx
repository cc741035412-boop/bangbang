import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { UploadSheet } from "./upload-sheet";

const mocks = vi.hoisted(() => ({ mutate: vi.fn(), reset: vi.fn() }));

vi.mock("../features/observations/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/observations/api")>();
  return {
    ...actual,
    useAreas: () => ({ data: [{ id: 7, code: "blocks", name: "建构区" }], isLoading: false, isError: false }),
    useChildren: () => ({
      data: [
        { id: 9, name: "幼儿A", classroom_id: 1 },
        { id: 10, name: "幼儿B", classroom_id: 1 },
      ],
      isLoading: false,
      isError: false,
    }),
    useSubmitCapture: () => ({ mutate: mocks.mutate, reset: mocks.reset, isPending: false, isError: false, error: null }),
  };
});

describe("UploadSheet", () => {
  beforeEach(() => {
    mocks.mutate.mockReset();
    mocks.reset.mockReset();
  });

  it("requires a child and passes the primary and extra children into capture", () => {
    render(<MemoryRouter><UploadSheet onClose={vi.fn()} onUploaded={vi.fn()} /></MemoryRouter>);
    const confirm = screen.getByRole("button", { name: "确认" });
    expect(confirm).toBeDisabled();

    const file = new File(["video"], "sample.mp4", { type: "video/mp4" });
    fireEvent.change(screen.getByLabelText("视频"), { target: { files: [file] } });
    fireEvent.change(screen.getByRole("combobox", { name: "游戏区域" }), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "幼儿A" }));
    fireEvent.click(screen.getByRole("button", { name: "幼儿B" }));
    expect(confirm).toBeEnabled();

    fireEvent.click(confirm);
    expect(mocks.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ areaId: 7, childId: 9, extraChildIds: [10], file }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });
});
