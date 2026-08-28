import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";

import { AppRoutes } from "./routes";

vi.mock("../features/auth/auth-context-value", () => ({
  useAuth: () => ({
    account: {
      id: 1,
      phone: "13800000001",
      teacher_id: 1,
      name: "教师A",
      kindergarten_id: 1,
      kindergarten_name: "测试幼儿园A",
      classroom_id: 1,
      classroom_name: "中一班",
      created_at: "2026-08-27T00:00:00Z",
    },
    enabled: true,
    isLoading: false,
  }),
}));

describe("AppRoutes", () => {
  it.each([
    ["/", "今日素材"],
    ["/capture", "今日素材"],
    ["/month", "本月素材"],
    ["/mine", "我的"],
    ["/observations/12/review", "正在打开这条记录…"],
    ["/observations/12", "正在打开观察记录…"],
    ["/settings", "基础信息设置"],
  ])("renders %s", (path, heading) => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
  });
});
