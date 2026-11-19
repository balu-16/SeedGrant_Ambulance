/**
 * Centralized backend API client (FastAPI, `/api/v1`) — web mirror of
 * client/services/api.ts.
 *
 * Single place for envelope unwrapping ({ success, data, error: { code,
 * message } }) and error mapping. Auth state lives in services/portalAuth.ts:
 * the access token is held in module memory only; on 401 the client runs a
 * single-flight POST /portal-auth/refresh (cookie + X-CSRF-Token) and retries
 * once — when the refresh fails mid-session the session is cleared and every
 * tab is told via BroadcastChannel("portal-auth") {type:"expired"}.
 *
 * In dev, Vite proxies `/api` → http://localhost:8000 (see vite.config.ts).
 * In production (Vercel) the backend URL comes from `VITE_API_URL`
 * (e.g. https://seedgrant-backend.onrender.com/api/v1).
 */

import { API_BASE, TIMEOUT_MS } from "@/services/apiBase";
import { ApiError } from "@/services/ApiError";
import {
  getAccessToken,
  notifySessionExpired,
  readCsrfToken,
  trySessionRefresh,
} from "@/services/portalAuth";
import type { ApiEnvelope, AuthUser } from "@/types/api";
import { normalizeRole } from "@/types/api";

export { ApiError } from "@/services/ApiError";

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  /** Attach Bearer token (default true). */
  auth?: boolean;
  /** Retry once after refresh on 401 (default true). */
  retry?: boolean;
  /** Send cookies (default "same-origin" — the fetch default). */
  credentials?: RequestCredentials;
  /** Attach X-CSRF-Token from the portal_csrf cookie. */
  csrf?: boolean;
}

/** Core request client — exported for sibling services (next phases). */
export async function request<T>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const {
    method = "GET",
    body,
    auth = true,
    retry = true,
    credentials = "same-origin",
    csrf = false,
  } = opts;
  const token = auth ? getAccessToken() : null;
  let res: Response;
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      res = await fetch(`${API_BASE}${path}`, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(csrf ? { "X-CSRF-Token": readCsrfToken() ?? "" } : {}),
        },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
        credentials,
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
  // Refresh once on expired access token, then retry the original request.
  if (res.status === 401 && auth && retry) {
    const refreshed = await trySessionRefresh();
    if (refreshed) {
      return request<T>(path, { ...opts, retry: false });
    }
    // Session is gone (revoked/expired) — clear local state and tell the
    // other tabs so no stale authenticated screen survives.
    notifySessionExpired();
    throw new ApiError(
      "Session expired — please log in again",
      401,
      "UNAUTHORIZED",
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

// ---- Auth verification ----

/** GET /auth/me — re-verify the signed-in account server-side. */
export async function apiMe(): Promise<AuthUser> {
  const me = await request<AuthUser>("/auth/me");
  return { ...me, role: normalizeRole(me.role) };
}
