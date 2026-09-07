import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { CandidateIndicators } from "./candidate-indicators";
import type { IndicatorOption, ObservationTag } from "../features/observations/api";

const indicatorOptions: IndicatorOption[] = [{
  indicator_code: "4.4",
  indicator_name: "试误与问题解决",
  dimension: "认知建构",
  level: 1,
  level_label: "初阶",
  description: "遇到困难时主动寻求帮助",
  has_quant_rule: false,
}];

const teacherTag: ObservationTag = {
  id: 9,
  observation_id: 1,
  indicator_code: "4.4",
  indicator_name: "试误与问题解决",
  level: 3,
  source: "teacher_added",
  accepted: true,
  confidence: null,
  ai_reason: null,
  rank_in_suggestion: null,
  created_at: "2026-08-23T00:00:00Z",
  resolved_at: "2026-08-23T00:00:00Z",
};

const aiTag: ObservationTag = {
  ...teacherTag,
  id: 10,
  source: "ai_suggested",
  accepted: null,
  confidence: 0.82,
  ai_reason: "白描原文：“反复调整后继续搭建”",
  rank_in_suggestion: 1,
};

describe("CandidateIndicators", () => {
  it("submits a teacher-added indicator with a separately selected level", async () => {
    const onAddTeacherTag = vi.fn().mockResolvedValue(undefined);
    render(
      <CandidateIndicators
        addingTeacherTag={false}
        indicatorOptions={indicatorOptions}
        onAddTeacherTag={onAddTeacherTag}
        onDecide={vi.fn()}
        tags={[]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /都没说到/ }));
    fireEvent.change(screen.getByLabelText("选择指标"), { target: { value: "4.4" } });
    fireEvent.click(screen.getByRole("button", { name: "高阶" }));
    fireEvent.click(screen.getByRole("button", { name: "确认补充" }));

    await waitFor(() => expect(onAddTeacherTag).toHaveBeenCalledWith("4.4", 3));
  });

  it("visually labels persisted teacher-added indicators", () => {
    render(
      <CandidateIndicators
        addingTeacherTag={false}
        indicatorOptions={indicatorOptions}
        onAddTeacherTag={vi.fn()}
        onDecide={vi.fn()}
        tags={[teacherTag]}
      />,
    );

    expect(screen.getByRole("heading", { name: "你补充的" })).toBeInTheDocument();
    expect(screen.getByText("4.4 试误与问题解决")).toBeInTheDocument();
    expect(screen.getByText("高阶")).toBeInTheDocument();
  });

  it("shows evidence and preserves accept or reject decisions", async () => {
    const onDecide = vi.fn();
    render(
      <CandidateIndicators
        addingTeacherTag={false}
        indicatorOptions={indicatorOptions}
        onAddTeacherTag={vi.fn()}
        onDecide={onDecide}
        tags={[aiTag]}
      />,
    );

    expect(screen.getByText(/较有把握/)).toBeInTheDocument();
    expect(screen.getByText(/反复调整后继续搭建/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "采用 试误与问题解决" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "不采用 试误与问题解决" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "不采用 试误与问题解决" }));

    expect(onDecide).toHaveBeenNthCalledWith(1, 10, true);
    expect(onDecide).toHaveBeenNthCalledWith(2, 10, false);
    await waitFor(() => expect(screen.getByRole("button", { name: "采用 试误与问题解决" })).toBeEnabled());
  });
  it("选择立即反馈，保存失败恢复原状并能重试", async () => {
    let rejectSave: (error: Error) => void = () => {};
    const pending = new Promise<void>((_resolve, reject) => { rejectSave = reject; });
    const onDecide = vi.fn().mockReturnValue(pending);
    render(<CandidateIndicators addingTeacherTag={false} indicatorOptions={indicatorOptions} onAddTeacherTag={vi.fn()} onDecide={onDecide} tags={[aiTag]} />);
    const adopt = screen.getByRole("button", { name: "采用 试误与问题解决" });
    fireEvent.click(adopt);
    expect(adopt).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("保存中");
    expect(adopt).toBeDisabled();
    await act(async () => { rejectSave(new Error("network")); });
    expect(screen.getByRole("alert")).toHaveTextContent("没有保存成功");
    expect(adopt).toHaveAttribute("aria-pressed", "false");
    expect(adopt).toBeEnabled();
  });

});
