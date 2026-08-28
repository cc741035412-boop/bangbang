import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { MockNarrativeNotice } from "./observation-review-page";

describe("MockNarrativeNotice", () => {
  it("shows the mock notice without demo=1", () => {
    render(
      <MemoryRouter initialEntries={["/observations/1/review"]}>
        <MockNarrativeNotice className="test" />
      </MemoryRouter>,
    );

    expect(screen.getByText("⚠️ 当前为演示数据，尚未接入真实 AI")).toBeInTheDocument();
  });

  it("hides the mock notice with demo=1", () => {
    render(
      <MemoryRouter initialEntries={["/observations/1/review?demo=1"]}>
        <MockNarrativeNotice className="test" />
      </MemoryRouter>,
    );

    expect(screen.queryByText("⚠️ 当前为演示数据，尚未接入真实 AI")).not.toBeInTheDocument();
  });
});
