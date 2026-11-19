/**
 * Auth state for the portal (contract §1/§9).
 *
 * Session flow:
 *   1. POST /api/v1/portal-auth/login { email, password }
 *      → { success, data: { access_token, user } } — access token held in
 *      module memory only (never localStorage); the refresh token lives in
 *      the server-set HttpOnly portal_rt cookie.
 *   2. Boot: POST /portal-auth/refresh (cookie + X-CSRF-Token) → GET /auth/me
 *      re-verifies role + scope. 401 → login screen; network failure → retry
 *      screen.
 *   3. DRIVER accounts are rejected (403 server-side + client guard).
 *   4. On any mid-session 401 the api client runs a single-flight
 *      /portal-auth/refresh and retries once; if the refresh fails the session
 *      is cleared here (user + query cache) and every other tab is told via
 *      BroadcastChannel("portal-auth") — no stale authenticated screen.
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
import { ApiError, apiMe } from "@/services/api";
import {
  onSessionEvent,
  portalLogin,
  portalLogout,
  portalRefresh,
} from "@/services/portalAuth";
import type { AuthUser } from "@/types/api";

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const bootstrapped = useRef(false);
  const queryClient = useQueryClient();

  // Any session-loss event (this tab's failed refresh or another tab's
  // logout/expired broadcast) clears user state + cache together, so a
  // revoked session never leaves a stale authenticated screen.
  const hardSignOut = useCallback(() => {
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(
    () => onSessionEvent(() => hardSignOut()),
    [hardSignOut],
  );

  // Boot: cookie refresh → access token in memory → /auth/me. Network
  // failure keeps a retry screen; 401 lands on the login screen.
  const runBoot = useCallback(async () => {
    setBootError(null);
    setBooting(true);
    try {
      await portalRefresh();
      const me = await apiMe();
      setUser(me);
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) {
        setBootError(e.message);
      } else {
        setUser(null);
      }
    } finally {
      setBooting(false);
    }
  }, []);

  // Bootstrap once (StrictMode-safe, like the original bootstrapped ref).
  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    void runBoot();
  }, [runBoot]);

  const login = useCallback(
    async (email: string, password: string): Promise<AuthUser> => {
      const u = await portalLogin(email, password);
      if (u.role === "driver") {
        // Drivers belong to the Expo app, not this portal (the server also
        // rejects them with 403 DRIVER_ROLE_NOT_ALLOWED — belt and braces).
        await portalLogout();
        throw new ApiError(
          "Driver accounts use the mobile app, not this portal.",
          403,
          "ROLE_NOT_ALLOWED",
        );
      }
      setUser(u);
      queryClient.clear();
      return u;
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    // portalLogout also emits {type:"logout"} → hardSignOut runs via the
    // listener; clearing here as well keeps the ordering deterministic.
    await portalLogout();
    hardSignOut();
  }, [hardSignOut]);

  const value = useMemo(
    () => ({ user, booting, bootError, retryBoot: runBoot, login, logout }),
    [user, booting, bootError, runBoot, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
