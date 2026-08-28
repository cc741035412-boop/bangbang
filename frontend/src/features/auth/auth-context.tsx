import type { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router";

import { FEATURES } from "../../config/features";
import { useMe } from "./api";
import { AuthContext, useAuth, type AuthState } from "./auth-context-value";

export function AuthProvider({ children }: PropsWithChildren) {
  const me = useMe();
  const value: AuthState = {
    account: me.data ?? null,
    enabled: FEATURES.auth,
    isLoading: FEATURES.auth && me.isLoading,
  };
  return <AuthContext value={value}>{children}</AuthContext>;
}

/**
 * 登录闸门。
 * FEATURES.auth 为 false 时整体放行——现在没有后端，不能把人挡在门外。
 */
export function RequireAuth({ children }: PropsWithChildren) {
  const { account, enabled, isLoading } = useAuth();
  const location = useLocation();

  if (!enabled) return <>{children}</>;
  if (isLoading) {
    return (
      <div className="grid min-h-dvh place-items-center text-sm text-ink-muted">
        正在确认登录状态…
      </div>
    );
  }
  if (!account) return <Navigate replace state={{ from: location.pathname }} to="/login" />;
  return <>{children}</>;
}
