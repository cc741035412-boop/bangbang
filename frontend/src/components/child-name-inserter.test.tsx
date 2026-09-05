import { fireEvent, render, screen } from "@testing-library/react";

import { ChildNameInserter } from "./child-name-inserter";

const children = [
  { id: 1, name: "幼儿A" },
  { id: 2, name: "幼儿B" },
];

describe("ChildNameInserter", () => {
  it("群体场景不提供「一键代入」，提示逐个指认", () => {
    render(
      <ChildNameInserter
        text="先有几名孩子在玩，穿白T恤的男孩蹲着。"
        children={children}
        selectedChildId={1}
        onApply={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /白描里有/ }));
    // 群体（几名孩子）场景：禁用一键代入
    expect(screen.queryByRole("button", { name: /一键代入/ })).toBeNull();
    expect(screen.getByText(/多个孩子/)).toBeTruthy();
  });

  it("无群体词（单一孩子）时提供「一键代入」", () => {
    render(
      <ChildNameInserter
        text="穿白T恤的男孩蹲着，旁边一个女孩看着。"
        children={children}
        selectedChildId={1}
        onApply={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /白描里有/ }));
    expect(screen.getByRole("button", { name: /一键代入/ })).toBeTruthy();
  });
});
