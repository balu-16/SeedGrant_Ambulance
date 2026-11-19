/**
 * Unit tests — services/api.ts request() auth flows with a mocked fetch:
 * envelope unwrapping, 401 → single-flight portal refresh → retry, and the
 * session-expired path (local event + ApiError) when the refresh fails.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, request } from "@/services/api";
import {
  clearSession,
  getAccessToken,
  getSessionUser,
  onSessionEvent,
  setSession,
} from "@/services/portalAuth";
import type { ApiEnvelope, AuthUser } from "@/types/api";

const USER: AuthUser = { id: "u1", email: "admin@demo.io", role: "admin" };

function jsonResponse(body: ApiEnvelope<unknown>, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe("request() auth flows", () => {
  beforeEach(() => {
    clearSession();
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    clearSession();
  });

  it("unwraps the {success,data,error} envelope", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ success: true, data: { hello: 1 } }));
    vi.stubGlobal("fetch", fetchMock);
    setSession("token-1", USER);

    await expect(request<{ hello: number }>("/thing")).resolves.toEqual({
      hello: 1,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer token-1",
    );
  });

  it("retries once through the portal refresh on 401", async () => {
    const fetchMock = vi
      .fn()
      // 1) original request → expired
      .mockResolvedValueOnce(jsonResponse({ success: false }, 401))
      // 2) POST /portal-auth/refresh → rotated token + user
      .mockResolvedValueOnce(
        jsonResponse({
          success: true,
          data: { access_token: "token-2", user: USER },
        }),
      )
      // 3) retried request → success
      .mockResolvedValueOnce(
        jsonResponse({ success: true, data: { ok: true } }),
      );
    vi.stubGlobal("fetch", fetchMock);
    setSession("token-1", USER);

    await expect(request("/admin/live")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const [, retryInit] = fetchMock.mock.calls[2] as [string, RequestInit];
    expect((retryInit.headers as Record<string, string>).Authorization).toBe(
      "Bearer token-2",
    );
    expect(getAccessToken()).toBe("token-2");
  });

  it("throws UNAUTHORIZED and emits {type:'expired'} when refresh fails mid-session", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ success: false }, 401))
      // refresh → session invalid
      .mockResolvedValueOnce(jsonResponse({ success: false }, 401));
    vi.stubGlobal("fetch", fetchMock);
    setSession("token-1", USER);

    const events: unknown[] = [];
    const unlisten = onSessionEvent((e) => events.push(e));

    await expect(request("/admin/live")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      code: "UNAUTHORIZED",
    } satisfies Partial<ApiError>);
    expect(events).toEqual([{ type: "expired" }]);
    expect(getAccessToken()).toBeNull();
    unlisten();
  });

  it("maps network failures to ApiError(0, NETWORK_ERROR)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("failed to fetch")),
    );
    await expect(request("/thing")).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
    });
  });

  it("surfaces envelope error codes as ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            { success: false, error: { code: "RELEASE_OUTSTANDING", message: "Release first" } },
            409,
          ),
        ),
    );
    const err = await request("/junctions/x/override", {
      method: "POST",
      body: {},
    }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("RELEASE_OUTSTANDING");
    expect((err as ApiError).status).toBe(409);
  });

  it("keeps the session user shape in memory only", () => {
    clearSession();
    expect(getAccessToken()).toBeNull();
    expect(getSessionUser()).toBeNull();
    setSession("t", USER);
    expect(getAccessToken()).toBe("t");
    expect(getSessionUser()?.email).toBe("admin@demo.io");
    clearSession();
    expect(getAccessToken()).toBeNull();
  });
});
