import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { ObservationGoals } from "./observation-goals";

function Editor({ initial = "" }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return <ObservationGoals onChange={setValue} presets={["目标一", "目标二", "目标三", "目标四"]} value={value} />;
}

describe("观察目标选择", () => {
  it("选超过三个目标仍可继续添加，空白不可添加，重复目标不重复计数", () => {
    render(<Editor />);
    for (const goal of ["目标一", "目标二", "目标三", "目标四"]) fireEvent.click(screen.getByRole("button", { name: goal }));
    expect(screen.getByText("已选 4 个")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "添加观察目标" }));
    expect(screen.getByRole("button", { name: "添加并选中" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("新的观察目标"), { target: { value: "目标一\n 自定义目标 \n" } });
    fireEvent.click(screen.getByRole("button", { name: "添加并选中" }));
    expect(screen.getByText("已选 5 个")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "自定义目标" })).toHaveAttribute("aria-pressed", "true");
  });

  it("恢复记录中的自定义目标，取消后本页仍能重新选择", () => {
    render(<Editor initial="自己的目标" />);
    const goal = screen.getByRole("button", { name: "自己的目标" });
    fireEvent.click(goal);
    expect(goal).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(goal);
    expect(goal).toHaveAttribute("aria-pressed", "true");
  });
});
