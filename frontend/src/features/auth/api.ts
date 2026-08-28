import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { HttpError, requestJson, writeToken } from "../../api/http";
import { FEATURES } from "../../config/features";

export interface AuthAccount {
  id: number;
  phone: string;
  /** 教师表主键，落款、归属都用它 */
  teacher_id: number;
  name: string;
  kindergarten_id: number | null;
  kindergarten_name: string | null;
  classroom_id: number | null;
  classroom_name: string | null;
  created_at: string;
}

export interface LoginResult {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  account: AuthAccount;
}

export interface RegisterBody {
  phone: string;
  code: string;
  name: string;
  kindergarten_name: string;
  classroom_name: string;
}

export const authKeys = {
  me: ["auth", "me"] as const,
};

/** 手机号：11 位、1 开头。前后端都要校验，这里只挡明显错的 */
export function isPhone(value: string) {
  return /^1\d{10}$/.test(value.trim());
}

export function isCode(value: string) {
  return /^\d{6}$/.test(value.trim());
}

export async function fetchMe(): Promise<AuthAccount | null> {
  if (!FEATURES.auth) return null;
  try {
    return await requestJson<AuthAccount>("/auth/me", {
      method: "GET",
      fallbackMessage: "登录状态确认失败",
    });
  } catch (error) {
    // 401 表示没登录或 token 过期，属于正常状态，不当作错误抛给页面
    if (error instanceof HttpError && error.status === 401) {
      writeToken(null);
      return null;
    }
    throw error;
  }
}

export function useMe() {
  return useQuery({
    queryKey: authKeys.me,
    queryFn: fetchMe,
    enabled: FEATURES.auth,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useSendCode() {
  return useMutation({
    mutationFn: async (phone: string) =>
      requestJson<{ expires_in: number; cooldown_sec: number }>("/auth/code", {
        method: "POST",
        body: JSON.stringify({ phone: phone.trim() }),
        fallbackMessage: "验证码没有发出去，请稍后再试",
      }),
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { phone: string; code: string }) =>
      requestJson<LoginResult>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ phone: body.phone.trim(), code: body.code.trim() }),
        fallbackMessage: "登录没有成功，请重试",
      }),
    onSuccess: async (result) => {
      writeToken(result.access_token);
      queryClient.setQueryData(authKeys.me, result.account);
      await queryClient.invalidateQueries();
    },
  });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: RegisterBody) =>
      requestJson<LoginResult>("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          phone: body.phone.trim(),
          code: body.code.trim(),
          name: body.name.trim(),
          kindergarten_name: body.kindergarten_name.trim(),
          classroom_name: body.classroom_name.trim(),
        }),
        fallbackMessage: "注册没有成功，请重试",
      }),
    onSuccess: async (result) => {
      writeToken(result.access_token);
      queryClient.setQueryData(authKeys.me, result.account);
      await queryClient.invalidateQueries();
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      try {
        await requestJson<void>("/auth/logout", {
          method: "POST",
          fallbackMessage: "退出登录没有完成",
        });
      } finally {
        // 后端失败也要清本地 token，否则用户被卡在一个退不出去的状态里
        writeToken(null);
      }
    },
    onSuccess: async () => {
      queryClient.setQueryData(authKeys.me, null);
      queryClient.clear();
    },
  });
}

/** 换绑手机号：老号验证码 + 新号验证码，两步都在同一个请求里提交 */
export function useChangePhone() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { new_phone: string; code: string }) =>
      requestJson<AuthAccount>("/auth/phone", {
        method: "PATCH",
        body: JSON.stringify({ new_phone: body.new_phone.trim(), code: body.code.trim() }),
        fallbackMessage: "手机号没有换成功",
      }),
    onSuccess: async (account) => {
      queryClient.setQueryData(authKeys.me, account);
    },
  });
}

/** 注销账号：不可逆，页面上必须二次确认 */
export function useDeleteAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (code: string) => {
      await requestJson<void>("/auth/account", {
        method: "DELETE",
        body: JSON.stringify({ code: code.trim() }),
        fallbackMessage: "账号注销没有完成",
      });
      writeToken(null);
    },
    onSuccess: () => {
      queryClient.clear();
    },
  });
}
