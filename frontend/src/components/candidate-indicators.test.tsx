import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
});
