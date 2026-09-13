/**
 * Centralized backend API client (FastAPI, `/api/v1`) — web mirror of
 * client/services/api.ts.
 *
 * Single place for the base URL, auth headers, single-flight token refresh,
 * envelope unwrapping ({ success, data, error: { code, message } }) and error
 * mapping. Pages/services must use this module — no hardcoded URLs elsewhere.
 *
 * In dev, Vite proxies `/api` → http://localhost:8000 (see vite.config.ts).
 * In production the built portal is mounted on the FastAPI origin at /admin,
 * so the same-origin `/api/v1` base keeps working unchanged.
 */

import {
  clearTokens,
  getTokens,
  saveTokens,
} from "@/services/tokenStorage";
import type { ApiEnvelope, AuthUser, LoginResponse, Tokens } from "@/types/api";

export { clearTokens, getTokens, saveTokens } from "@/services/tokenStorage";

const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(message: string, status = 0, code = "UNKNOWN") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  /** Attach Bearer token (default true). */
  auth?: boolean;
  /** Retry once after refresh on 401 (default true). */
  retry?: boolean;
}

/**
 * Single-flight refresh: concurrent 401s share one POST /auth/refresh call,
 * so a burst of expired requests never burns several refresh tokens.
 */
let refreshInFlight: Promise<boolean> | null = null;

function tryRefresh(refreshToken: string): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        const payload = (await res.json()) as ApiEnvelope<Tokens>;
        if (res.ok && payload.success && payload.data?.access_token) {
          saveTokens(payload.data);
          return true;
        }
        return false;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

/** Core request client — exported for sibling services (next phases). */
export async function request<T>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, auth = true, retry = true } = opts;
  const tokens = auth ? getTokens() : null;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(tokens ? { Authorization: `Bearer ${tokens.access_token}` } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  } catch (e) {
    throw new ApiError(
      e instanceof Error ? `Network error: ${e.message}` : "Network error",
      0,
      "NETWORK_ERROR",
    );
  }
  // Refresh once on expired access token, then retry the original request.
  if (res.status === 401 && auth && retry && tokens) {
    const refreshed = await tryRefresh(tokens.refresh_token);
    if (refreshed) {
      return request<T>(path, { ...opts, retry: false });
    }
    clearTokens();
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

// ---- Auth (backend field names match server schemas) ----

export async function apiLogin(
  email: string,
  password: string,
): Promise<LoginResponse> {
  const data = await request<LoginResponse>("/auth/login", {
    method: "POST",
    body: { email, password },
    auth: false,
    retry: false,
  });
  saveTokens({
    access_token: data.access_token,
    refresh_token: data.refresh_token,
  });
  return data;
}

export async function apiMe(): Promise<AuthUser> {
  return request<AuthUser>("/auth/me");
}

export async function apiLogout(): Promise<void> {
  try {
    await request("/auth/logout", { method: "POST", retry: false });
  } catch {
    // Best effort — tokens are cleared regardless (see below).
  } finally {
    clearTokens();
  }
}
