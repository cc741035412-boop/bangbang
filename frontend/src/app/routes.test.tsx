import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";

import { AppRoutes } from "./routes";

describe("AppRoutes", () => {
  it.each([
    ["/", "今日素材"],
    ["/capture", "快速沉淀"],
    ["/observations/12/review", "正在打开这条记录…"],
    ["/observations/12", "正在打开观察记录…"],
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
