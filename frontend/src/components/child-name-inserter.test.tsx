import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ChildNameInserter } from "./child-name-inserter";
import type { ObservationPeople } from "../features/observations/api";
const children = [{ id: 1, name: "测试甲" }, { id: 2, name: "测试乙" }];
const people: ObservationPeople = {
  narrative: "幼儿A穿红衣。幼儿B穿蓝衣。幼儿A搭建。孩子们围观。",
  method: "aliases", notice: "请核对衣着和行为。",
  refs: [
    { start: 0, end: 3, token: "幼儿A", group: false, clue: "幼儿A穿红衣。" },
    { start: 7, end: 10, token: "幼儿B", group: false, clue: "幼儿B穿蓝衣。" },
    { start: 14, end: 17, token: "幼儿A", group: false, clue: "幼儿A搭建。" },
    { start: 20, end: 23, token: "孩子们", group: true, clue: "孩子们围观。" },
  ],
  people: [{ label: "人物 1", ref_indexes: [0, 2], clues: ["幼儿A穿红衣。", "幼儿A搭建。"] }, { label: "人物 2", ref_indexes: [1], clues: ["幼儿B穿蓝衣。"] }],
};
it("两个人多次出现，只对应两次；群体不代入", async () => {
  const onApply = vi.fn().mockResolvedValue(undefined);
  render(<ChildNameInserter people={people} children={children} loading={false} error={false} onRetry={vi.fn()} onApply={onApply} />);
  expect(screen.getAllByRole("combobox")).toHaveLength(2);
  expect(screen.getByText("将一起代入 2 处称呼")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("人物 1"), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText("人物 2"), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "确认人物并代入姓名" }));
  await waitFor(() => expect(onApply).toHaveBeenCalledWith([{ ref_indexes: [0, 2], child_id: 1 }, { ref_indexes: [1], child_id: 2 }], people.narrative));
});
it("老师发现分组不对时能拆开，保存失败保留选择供重试", async () => {
  const onApply = vi.fn().mockRejectedValue(new Error("姓名未保存"));
  render(<ChildNameInserter people={people} children={children} loading={false} error={false} onRetry={vi.fn()} onApply={onApply} />);
  fireEvent.click(screen.getByText("分组不对？拆开核对"));
  fireEvent.click(screen.getByRole("button", { name: "拆开人物 1" }));
  expect(screen.getAllByRole("combobox")).toHaveLength(3);
  fireEvent.change(screen.getByLabelText("人物 1"), { target: { value: "1" } });
  fireEvent.click(screen.getByRole("button", { name: "确认人物并代入姓名" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("姓名未保存");
  expect(screen.getByLabelText("人物 1")).toHaveValue("1");
});
