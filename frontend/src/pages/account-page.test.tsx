import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { AccountPage } from "./account-page";

const authMocks = vi.hoisted(() => ({
  changePhone: vi.fn(),
  deleteAccount: vi.fn(),
  logout: vi.fn(),
  resetSendCode: vi.fn(),
  sendCode: vi.fn(),
}));

vi.mock("../features/auth/auth-context-value", () => ({
  useAuth: () => ({
    account: {
      id: 1,
      phone: "13800000201",
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

vi.mock("../features/auth/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/auth/api")>();
  return {
    ...actual,
    useSendCode: () => ({
      error: null,
      isError: false,
      isPending: false,
      mutate: authMocks.sendCode,
      reset: authMocks.resetSendCode,
    }),
    useChangePhone: () => ({
      error: null,
      isError: false,
      isPending: false,
      mutate: authMocks.changePhone,
    }),
    useDeleteAccount: () => ({
      error: null,
      isError: false,
      isPending: false,
      mutate: authMocks.deleteAccount,
    }),
    useLogout: () => ({ isPending: false, mutate: authMocks.logout }),
  };
});

describe("AccountPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authMocks.sendCode.mockImplementation(
      (_phone: string, options?: { onSuccess?: () => void }) => options?.onSuccess?.(),
    );
  });

  it("shows send confirmation and a cooldown after requesting a change-phone code", () => {
    render(<MemoryRouter><AccountPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole("button", { name: "更换手机号" }));
    fireEvent.change(screen.getByPlaceholderText("新手机号"), {
      target: { value: "13800000202" },
    });
    fireEvent.click(screen.getByRole("button", { name: "获取验证码" }));

    expect(authMocks.sendCode).toHaveBeenCalledWith(
      "13800000202",
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(screen.getByRole("button", { name: "60 秒后重发" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("验证码已发送，5 分钟内有效。");
  });
});
