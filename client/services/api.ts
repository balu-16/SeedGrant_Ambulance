/**
 * Centralized backend API client (FastAPI, `/api/v1`).
 *
 * Single place for the base URL, auth headers, token refresh, envelope
 * unwrapping, and error mapping. Screens/services must use this module —
 * no hardcoded URLs elsewhere.
 *
 * Offline behavior: when `EXPO_PUBLIC_API_URL` is empty or the backend is
 * unreachable, calls throw `ApiError` (`API_DISABLED` / `NETWORK_ERROR`)
 * callers surface an error instead of fabricating data.
 */

import { clearTokens, getTokens, saveTokens } from "./tokenStorage";

export { clearTokens, getTokens, saveTokens } from "./tokenStorage";

export interface BackendTokens {
  access_token: string;
  refresh_token: string;
}

export interface BackendUser {
  id: string;
  email: string;
  role: string;
}

export function apiBaseUrl(): string {
  const raw = (process.env.EXPO_PUBLIC_API_URL ?? "").trim();
  return raw.replace(/\/+$/, "");
}

/** False when no backend is configured — the app shows its config-required screen. */
export function isApiEnabled(): boolean {
  return apiBaseUrl().length > 0;
}

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

/** True when API is configured AND we hold tokens from a backend login. */
export async function isBackendLinked(): Promise<boolean> {
  return isApiEnabled() && (await getTokens()) !== null;
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
 * Storage + fetch seams — injectable so node unit tests can exercise the
 * refresh/401 machinery without the native token stores. Production callers
 * use request(), which wires the real implementations.
 */
export interface ApiDeps {
  getTokens(): Promise<BackendTokens | null>;
  saveTokens(tokens: BackendTokens): Promise<void>;
  clearTokens(): Promise<void>;
  fetchImpl: typeof fetch;
}

function defaultDeps(): ApiDeps {
  return { getTokens, saveTokens, clearTokens, fetchImpl: fetch };
}

/** Core request client — exported for sibling services (see emergency.ts). */
export function request<T>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  return requestCore<T>(defaultDeps(), path, opts);
}

/** The request loop with injectable seams (exported for node unit tests). */
export async function requestCore<T>(
  deps: ApiDeps,
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const base = apiBaseUrl();
  if (!base) {
    throw new ApiError("Backend not configured", 0, "API_DISABLED");
  }
  const { method = "GET", body, auth = true, retry = true } = opts;
  const tokens = auth ? await deps.getTokens() : null;
  let res: Response;
  try {
    res = await deps.fetchImpl(`${base}/api/v1${path}`, {
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
    const refreshed = await tryRefresh(deps, tokens.refresh_token);
    if (refreshed === "ok") {
      return requestCore<T>(deps, path, { ...opts, retry: false });
    }
    if (refreshed === "rejected") {
      // The server explicitly revoked/rejected the refresh token — the
      // session is truly gone, so drop the tokens and force a login.
      await deps.clearTokens();
      throw new ApiError(
        "Session expired — please log in again",
        401,
        "UNAUTHORIZED",
      );
    }
    // Transient network/server failure during refresh: the tokens may still
    // be perfectly valid, so keep them and surface a retryable error.
    throw new ApiError(
      "Connection lost while refreshing the session",
      0,
      "NETWORK_ERROR",
    );
  }
  let payload: {
    success?: boolean;
    data?: T;
    error?: { code?: string; message?: string };
  };
  try {
    payload = (await res.json()) as typeof payload;
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

type RefreshOutcome = "ok" | "rejected" | "offline";

/**
 * Single-flight refresh: concurrent 401s share one POST /auth/refresh call.
 * The server rotates refresh tokens on every refresh, so without this a
 * burst of expired requests would burn several tokens and log the user out.
 */
let refreshInFlight: Promise<RefreshOutcome> | null = null;

function tryRefresh(
  deps: ApiDeps,
  refreshToken: string,
): Promise<RefreshOutcome> {
  if (!refreshInFlight) {
    refreshInFlight = (async (): Promise<RefreshOutcome> => {
      try {
        const base = apiBaseUrl();
        const res = await deps.fetchImpl(`${base}/api/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        const payload = (await res.json()) as {
          success?: boolean;
          data?: BackendTokens;
        };
        if (res.ok && payload.success && payload.data?.access_token) {
          await deps.saveTokens(payload.data);
          return "ok";
        }
        // Explicit rejection means the token is revoked/invalid; anything
        // else (5xx, malformed body, transport error) is treated as offline.
        return res.status === 401 || res.status === 400
          ? "rejected"
          : "offline";
      } catch {
        return "offline";
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

// ---- Auth (backend field names match server schemas) ----

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: BackendUser;
}

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
  await saveTokens({
    access_token: data.access_token,
    refresh_token: data.refresh_token,
  });
  return data;
}

export async function apiLogout(): Promise<void> {
  try {
    await request("/auth/logout", { method: "POST" });
  } catch {
    // Best effort — tokens are cleared regardless (see below).
  } finally {
    await clearTokens();
  }
}

export async function apiMe(): Promise<BackendUser> {
  return request<BackendUser>("/auth/me");
}

export async function apiChangePassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ changed: boolean }> {
  return request<{ changed: boolean }>("/auth/change-password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

export interface BackendProfile {
  name: string;
  phone: string;
  region: string;
  hospital: string;
  control_center: string;
}

export async function apiGetProfile(): Promise<BackendProfile> {
  return request<BackendProfile>("/auth/profile");
}

export async function apiUpdateProfile(
  patch: Partial<BackendProfile>,
): Promise<BackendProfile> {
  return request<BackendProfile>("/auth/profile", {
    method: "PATCH",
    body: {
      name: patch.name ?? "",
      phone: patch.phone ?? "",
      region: patch.region ?? "",
      hospital: patch.hospital ?? "",
      control_center: patch.control_center ?? "",
    },
  });
}

// ---- Driver resources ----

export interface BackendAmbulance {
  id: string;
  vehicle_no: string;
  driver_id: string | null;
}

export async function apiMyAmbulance(): Promise<BackendAmbulance> {
  return request<BackendAmbulance>("/ambulances/mine");
}
