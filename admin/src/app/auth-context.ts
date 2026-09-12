/**
 * Auth context + hook (kept separate from AuthProvider so fast refresh sees
 * one component export per file).
 */

import { createContext, useContext } from "react";
import type { AuthUser } from "@/types/api";

export interface AuthContextValue {
  /** Signed-in portal user (null when logged out). */
  user: AuthUser | null;
  /** True while the stored-token bootstrap (/auth/me) is running. */
  booting: boolean;
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
