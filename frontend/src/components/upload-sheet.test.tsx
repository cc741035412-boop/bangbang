import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { UploadSheet } from "./upload-sheet";

const mocks = vi.hoisted(() => ({ mutate: vi.fn(), reset: vi.fn() }));

vi.mock("../features/observations/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/observations/api")>();
  return {
    ...actual,
    useAreas: () => ({ data: [{ id: 7, code: "blocks", name: "建构区" }], isLoading: false, isError: false }),
    useSubmitCapture: () => ({ mutate: mocks.mutate, reset: mocks.reset, isPending: false, isError: false, error: null }),
  };
});

describe("UploadSheet", () => {
  beforeEach(() => {
    mocks.mutate.mockReset();
    mocks.reset.mockReset();
  });

  it("要求先选文件和游戏区域，再一次性提交（快速存素材）", () => {
    render(<MemoryRouter><UploadSheet onClose={vi.fn()} onUploaded={vi.fn()} /></MemoryRouter>);

    const submit = screen.getByRole("button", { name: "上传并继续" });
    // 没选文件、没选区域时按钮不可点
    expect(submit).toBeDisabled();

    const file = new File(["image"], "photo.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("照片"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("radio", { name: "建构区" }));

    // 文件 + 区域都选好后才能提交
    expect(submit).toBeEnabled();

    fireEvent.click(submit);
    expect(mocks.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ areaId: 7, file }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("选了不支持的格式会给出提示且不能提交", () => {
    render(<MemoryRouter><UploadSheet onClose={vi.fn()} onUploaded={vi.fn()} /></MemoryRouter>);

    const submit = screen.getByRole("button", { name: "上传并继续" });
    const file = new File(["data"], "notes.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText("照片"), { target: { files: [file] } });

    expect(screen.getByRole("alert")).toHaveTextContent("只支持照片和视频");
    expect(submit).toBeDisabled();
  });
});
