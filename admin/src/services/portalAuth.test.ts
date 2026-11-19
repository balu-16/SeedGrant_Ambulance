/**
 * Unit tests — services/portalAuth.ts: login/refresh/logout endpoint calls
 * (mocked fetch), CSRF cookie parsing, in-memory session state and the
 * session-event fan-out (local listeners + BroadcastChannel messages).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearSession,
  notifySessionExpired,
  onSessionEvent,
  portalLogin,
  portalLogout,
  portalRefresh,
  readCsrfToken,
  setSession,
  trySessionRefresh,
  LEGACY_TOKENS_KEY,
} from "@/services/portalAuth";
import type { ApiEnvelope, AuthUser } from "@/types/api";

const USER: AuthUser = { id: "u2", email: "police@demo.io", role: "police" };

function jsonResponse(body: ApiEnvelope<unknown>, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

function setCookie(name: string, value: string) {
  document.cookie = `${name}=${value}; path=/`;
}

describe("portalAuth", () => {
  beforeEach(() => {
    clearSession();
    vi.unstubAllGlobals();
    document.cookie = "portal_csrf=; path=/; max-age=0";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearSession();
  });

  it("removes the legacy localStorage token key on module init", async () => {
    localStorage.setItem(LEGACY_TOKENS_KEY, '{"access_token":"x"}');
    // Re-run the module body: its init deletes the pre-portal-auth tokens so
    // stale sessions always land on a clean sign-in (contract §9).
    vi.resetModules();
    await import("@/services/portalAuth");
    expect(localStorage.getItem(LEGACY_TOKENS_KEY)).toBeNull();
  });

  it("portalLogin posts credentials and stores the session in memory", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({
          success: true,
          data: { access_token: "tok", user: { ...USER, role: "POLICE" } },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const user = await portalLogin("police@demo.io ", "pw");
    expect(user.role).toBe("police"); // normalized from the server's POLICE
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/portal-auth/login");
    expect(JSON.parse(init.body as string)).toEqual({
      email: "police@demo.io",
      password: "pw",
    });
  });

  it("portalRefresh sends the CSRF header and rotates the memory token", async () => {
    setCookie("portal_csrf", "csrf-123");
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({
          success: true,
          data: { access_token: "tok-2", user: USER },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const user = await portalRefresh();
    expect(user.email).toBe(USER.email);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/portal-auth/refresh");
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe(
      "csrf-123",
    );
    expect(init.credentials).toBe("same-origin");
  });

  it("portalRefresh throws UNAUTHORIZED on invalid session and NETWORK_ERROR when unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ success: false }, 401)),
    );
    await expect(portalRefresh()).rejects.toMatchObject({
      status: 401,
      code: "UNAUTHORIZED",
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("down")),
    );
    await expect(portalRefresh()).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
    });
  });

  it("portalLogout posts with CSRF, clears memory and emits {type:'logout'}", async () => {
    setCookie("portal_csrf", "csrf-9");
    setSession("tok", USER);
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ success: true, data: { logged_out: true } }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const events: unknown[] = [];
    const unlisten = onSessionEvent((e) => events.push(e));
    await portalLogout();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/portal-auth/logout");
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe(
      "csrf-9",
    );
    expect(events).toEqual([{ type: "logout" }]);
    unlisten();
  });

  it("readCsrfToken parses the portal_csrf cookie", () => {
    expect(readCsrfToken()).toBeNull();
    setCookie("portal_csrf", "abc%2Fdef");
    expect(readCsrfToken()).toBe("abc/def");
    document.cookie = "portal_csrf=; path=/; max-age=0";
    expect(readCsrfToken()).toBeNull();
  });

  it("notifySessionExpired emits only when a session existed (boot next to a signed-in tab must not clear it)", () => {
    const events: unknown[] = [];
    const unlisten = onSessionEvent((e) => events.push(e));
    notifySessionExpired();
    expect(events).toEqual([]);
    setSession("t", USER);
    notifySessionExpired();
    expect(events).toEqual([{ type: "expired" }]);
    unlisten();
  });

  it("trySessionRefresh is single-flight under concurrency", async () => {
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve(
                jsonResponse({
                  success: true,
                  data: { access_token: "tok", user: USER },
                }),
              ),
            10,
          ),
        ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const [a, b] = await Promise.all([
      trySessionRefresh(),
      trySessionRefresh(),
    ]);
    expect(a).toBe(true);
    expect(b).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
