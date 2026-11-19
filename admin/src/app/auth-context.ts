/**
 * Auth context + hook (kept separate from AuthProvider so fast refresh sees
 * one component export per file).
 */

import { createContext, useContext } from "react";
import type { AuthUser } from "@/types/api";

export interface AuthContextValue {
  /** Signed-in portal user (null when logged out). */
  user: AuthUser | null;
  /** True while the boot refresh (/portal-auth/refresh + /auth/me) runs. */
  booting: boolean;
  /**
   * Boot failure message set only when the server is unreachable
   * (NETWORK_ERROR) — the login redirect covers session-invalid boots.
   */
  bootError: string | null;
  /** Re-run the boot sequence from the BootScreen retry button. */
  retryBoot: () => void;
  login: (email: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within <AuthProvider>");
  }
  return ctx;
}
