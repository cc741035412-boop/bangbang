import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

import { ChildProfilePage } from "./child-profile-page";

vi.mock("../features/children/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/children/api")>();
  return {
    ...actual,
    useChildProfile: () => ({
      isLoading: false,
      isError: false,
      data: {
        id: 1,
        name: "幼儿A",
        classroom_id: 1,
        classroom_name: "中一班",
        birth_date: null,
        gender: "female",
        created_at: "2026-08-26T01:00:00Z",
        media_count: 2,
        record_count: 1,
        observed_day_count: 2,
        dimension_counts: { 身体参与: 1, 社会互动: 0, 认知建构: 99 },
        records: [{
          observation_id: 12,
          title: "建构区观察记录",
          area_name: "建构区",
          observed_at: "2026-08-27T01:00:00Z",
          dimensions: ["身体参与"],
          exported: false,
        }],
      },
    }),
  };
});

describe("ChildProfilePage", () => {
  it("只展示事实计数和两个合规维度", () => {
    render(
      <MemoryRouter initialEntries={["/children/1"]}>
        <Routes>
          <Route element={<ChildProfilePage />} path="children/:childId" />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "幼儿档案" })).toBeInTheDocument();
    expect(screen.getByText("幼儿A")).toBeInTheDocument();
    expect(screen.getByText("建构区观察记录")).toBeInTheDocument();
    expect(screen.getAllByText("身体参与").length).toBeGreaterThan(0);
    expect(screen.getByText("社会互动")).toBeInTheDocument();
    expect(screen.queryByText("认知建构")).not.toBeInTheDocument();
    expect(screen.getByText(/不代表孩子在这方面的水平/)).toBeInTheDocument();
  });
});
