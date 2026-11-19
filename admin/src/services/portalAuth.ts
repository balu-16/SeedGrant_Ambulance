/**
 * Portal session auth (contract §1/§9) — memory-only access token.
 *
 * The access token NEVER touches localStorage/sessionStorage: it lives in
 * module memory for the lifetime of the tab. The refresh token stays in the
 * server-set HttpOnly `portal_rt` cookie; the readable `portal_csrf` cookie
 * travels back as the X-CSRF-Token header on refresh + logout.
 *
 * Cross-tab coordination uses BroadcastChannel("portal-auth") with
 * {type:"logout"} and {type:"expired"} messages: the sender posts on logout
 * and on mid-session refresh failure; every tab (including this one, via the
 * local listener) clears user state + query cache on receipt.
 *
 * Legacy cleanup: the pre-portal-auth localStorage token key is deleted on
 * first load so stale sessions always land on a clean sign-in.
 */

import { API_BASE, TIMEOUT_MS } from "@/services/apiBase";
import { ApiError } from "@/services/ApiError";
import type { ApiEnvelope, AuthUser } from "@/types/api";
import { normalizeRole } from "@/types/api";

/** localStorage key used before portal-auth — remove it once on boot. */
export const LEGACY_TOKENS_KEY = "admin-portal:tokens:v1";

try {
  localStorage.removeItem(LEGACY_TOKENS_KEY);
} catch {
  // Storage unavailable (private mode etc.) — nothing to clean up.
}

// ---- In-memory session (never persisted) ----

let accessToken: string | null = null;
let currentUser: AuthUser | null = null;

/** Current in-memory access token (null when signed out). */
export function getAccessToken(): string | null {
  return accessToken;
}

export function setSession(token: string, user: AuthUser): void {
  accessToken = token;
  currentUser = { ...user, role: normalizeRole(user.role) };
}

export function getSessionUser(): AuthUser | null {
  return currentUser;
}

export function clearSession(): void {
  accessToken = null;
  currentUser = null;
}

// ---- CSRF cookie (readable, set by the backend at login) ----

/** Value of the `portal_csrf` cookie, or null when absent. */
export function readCsrfToken(): string | null {
  try {
    for (const part of document.cookie.split(";")) {
      const [name, ...rest] = part.trim().split("=");
      if (name === "portal_csrf") {
        return decodeURIComponent(rest.join("="));
      }
    }
  } catch {
    // document.cookie unavailable — fall through.
  }
  return null;
}

// ---- Shared POST for the three portal-auth endpoints ----

async function callPortalAuth<T>(
  path: string,
  opts: { csrf?: boolean; body?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (opts.csrf) {
    const csrf = readCsrfToken();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  let res: Response;
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      res = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers,
        credentials: "same-origin",
        ...(opts.body !== undefined ? { body: JSON.stringify(opts.body) } : {}),
        signal: ctrl.signal,
      });
    } finally {
      clearTimeout(timer);
    }
  } catch (e) {
    throw new ApiError(
      e instanceof Error
        ? e.name === "AbortError"
          ? "Request timed out — please retry"
          : `Network error: ${e.message}`
        : "Network error",
      0,
      "NETWORK_ERROR",
    );
  }
  let payload: ApiEnvelope<T>;
  try {
    payload = (await res.json()) as ApiEnvelope<T>;
  } catch {
    throw new ApiError(
      `Bad response (${res.status})`,
      res.status,
      "BAD_RESPONSE",
    );
  }
  if (!res.ok || payload.success === false || payload.data === undefined) {
    throw new ApiError(
      payload.error?.message ?? `Request failed (${res.status})`,
      res.status,
      payload.error?.code ?? "REQUEST_FAILED",
    );
  }
  return payload.data;
}

// ---- Cross-tab + in-tab session event fan-out ----

export type PortalAuthEvent = { type: "logout" | "expired" };

const CHANNEL_NAME = "portal-auth";
type Listener = (event: PortalAuthEvent) => void;

const listeners = new Set<Listener>();
let channel: BroadcastChannel | null = null;

function getChannel(): BroadcastChannel | null {
  if (channel) return channel;
  if (typeof BroadcastChannel === "undefined") return null;
  try {
    channel = new BroadcastChannel(CHANNEL_NAME);
    channel.onmessage = (msg: MessageEvent) => {
      const data = (msg as MessageEvent<PortalAuthEvent>).data;
      if (data?.type === "logout" || data?.type === "expired") {
        listeners.forEach((l) => l(data));
      }
    };
  } catch {
    channel = null;
  }
  return channel;
}

/** Subscribe to session-loss events (local + other tabs). Returns unlisten. */
export function onSessionEvent(listener: Listener): () => void {
  getChannel();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Fire an event locally (this tab) and to every other tab. */
function emit(event: PortalAuthEvent): void {
  listeners.forEach((l) => l(event));
  getChannel()?.postMessage(event);
}

// ---- Endpoints (contract §1) ----

/** POST /portal-auth/login — portal credentials, driver rejected server-side. */
export async function portalLogin(
  email: string,
  password: string,
): Promise<AuthUser> {
  const data = await callPortalAuth<{ access_token: string; user: AuthUser }>(
    "/portal-auth/login",
    { body: { email: email.trim(), password } },
  );
  const user = { ...data.user, role: normalizeRole(data.user.role) };
  setSession(data.access_token, user);
  return user;
}

/**
 * POST /portal-auth/refresh — cookie + X-CSRF-Token (no body). Rotates the
 * refresh cookie and returns a fresh access token + user. Throws
 * ApiError(0, NETWORK_ERROR) when the server is unreachable and
 * ApiError(401, UNAUTHORIZED) when the session is invalid/absent — boot uses
 * that split to pick between the retry screen and the login screen.
 */
export async function portalRefresh(): Promise<AuthUser> {
  let data: { access_token: string; user: AuthUser };
  try {
    data = await callPortalAuth<{ access_token: string; user: AuthUser }>(
      "/portal-auth/refresh",
      { csrf: true },
    );
  } catch (e) {
    // No session to keep alive — surface only real network failures to boot.
    if (e instanceof ApiError && e.status === 0) throw e;
    throw new ApiError(
      "Session expired — please log in again",
      401,
      "UNAUTHORIZED",
    );
  }
  const user = { ...data.user, role: normalizeRole(data.user.role) };
  setSession(data.access_token, user);
  return user;
}

/**
 * POST /portal-auth/logout — revoke the server session and clear cookies
 * (best effort: memory is cleared regardless). Broadcasts {type:"logout"}.
 */
export async function portalLogout(): Promise<void> {
  try {
    await callPortalAuth("/portal-auth/logout", { csrf: true });
  } catch {
    // Idempotent server-side; sign the tab out even if the call failed.
  } finally {
    clearSession();
    emit({ type: "logout" });
  }
}

// ---- Single-flight mid-session refresh (used by services/api.ts) ----

let refreshInFlight: Promise<boolean> | null = null;

/**
 * Single-flight refresh: concurrent 401s share one POST /portal-auth/refresh
 * so a burst of expired requests never hammers the endpoint. Resolves false
 * when the session is gone (cookies cleared by the server response).
 */
export function trySessionRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        await portalRefresh();
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

/**
 * Fired by the api client when a mid-session refresh fails: clears the local
 * session and tells every tab ({type:"expired"}) so no stale authenticated
 * screen survives a revoked/expired portal session. No-op when this tab never
 * held a session (e.g. a fresh boot next to a signed-in tab must not clear it).
 */
export function notifySessionExpired(): void {
  const hadSession = accessToken !== null || currentUser !== null;
  clearSession();
  if (hadSession) emit({ type: "expired" });
}
