import { createContext, use } from "react";

import { FEATURES } from "../../config/features";
import type { AuthAccount } from "./api";

export interface AuthState {
  account: AuthAccount | null;
  /** 登录能力是否已接入后端 */
  enabled: boolean;
  isLoading: boolean;
}

export const AuthContext = createContext<AuthState>({
  account: null,
  enabled: FEATURES.auth,
  isLoading: false,
});

export function useAuth() {
  return use(AuthContext);
}
