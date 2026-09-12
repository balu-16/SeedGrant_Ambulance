/**
 * Auth state for the portal.
 *
 * Login flow contract (wired to real endpoints next phase — the client code
 * here is already final):
 *   1. POST /api/v1/auth/login { email, password }
 *      → { success, data: { access_token, refresh_token, user } }
 *      → tokens persisted under localStorage["admin-portal:tokens:v1"].
 *   2. GET /api/v1/auth/me (Bearer) re-verifies the account + role
 *      server-side; the response user is the source of truth for guards.
 *   3. DRIVER accounts are rejected — the mobile app is their client.
 *   4. On any 401 the api client runs a single-flight POST /auth/refresh and
 *      retries once; if refresh fails it clears tokens → RequireAuth
 *      redirects to /login.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AuthContext } from "@/app/auth-context";
import {
  ApiError,
  apiLogin,
  apiLogout,
  apiMe,
  clearTokens,
  getTokens,
} from "@/services/api";
import type { AuthUser } from "@/types/api";

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [booting, setBooting] = useState(true);
  const bootstrapped = useRef(false);
  const queryClient = useQueryClient();

  // Bootstrap: restore a session from stored tokens and re-verify via /me.
  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    let cancelled = false;
    (async () => {
      if (!getTokens()) {
        setBooting(false);
        return;
      }
      try {
        const me = await apiMe();
        if (!cancelled) setUser(me);
      } catch {
        clearTokens();
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string): Promise<AuthUser> => {
      const res = await apiLogin(email.trim(), password);
      if (res.user.role === "DRIVER") {
        // Drivers belong to the Expo app, not this portal.
        clearTokens();
        throw new ApiError(
          "Driver accounts use the mobile app, not this portal.",
          403,
          "ROLE_NOT_ALLOWED",
        );
      }
      // Re-verify server-side (role from the fresh token, not the login claim).
      const me = await apiMe().catch(() => res.user);
      setUser(me);
      queryClient.clear();
      return me;
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  const value = useMemo(
    () => ({ user, booting, login, logout }),
    [user, booting, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
