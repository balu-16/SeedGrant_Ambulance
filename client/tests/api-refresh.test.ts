/**
 * Unit tests for the api client's refresh/401 machinery (single-flight
 * rotation — the logic whose absence caused spurious logouts) and the
 * backend session-id lifecycle in emergency.ts. Uses the injectable ApiDeps
 * seams and a stubbed global fetch — no native storage or real network.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { requestCore, ApiError, type ApiDeps } from "../services/api";
import {
  backendGps,
  backendStop,
  retrackBackendSession,
  stopActiveBackendSession,
  __getActiveBackendSessionId,
} from "../services/emergency";

// apiBaseUrl() reads the env at call time, so this can follow the imports.
process.env.EXPO_PUBLIC_API_URL = "http://testserver";

interface Call {
  url: string;
  method: string;
  auth: string | null;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function makeDeps(
  respond?: (call: Call) => Response,
  opts: { failRefreshTransport?: boolean } = {},
) {
  const calls: Call[] = [];
  let tokens: { access_token: string; refresh_token: string } | null = {
    access_token: "AT-1",
    refresh_token: "RT-1",
  };
  let cleared = false;
  const fetchImpl: typeof fetch = async (input, init) => {
    const url = String(input);
    const call: Call = {
      url,
      method: (init?.method as string) ?? "GET",
      auth:
        (init?.headers as Record<string, string> | undefined)?.Authorization ??
        null,
    };
    calls.push(call);
    if (opts.failRefreshTransport && url.includes("/auth/refresh")) {
      throw new TypeError("simulated network failure");
    }
    if (respond) return respond(call);
    return jsonResponse({ success: true, data: {} });
  };
  const deps: ApiDeps = {
    getTokens: async () => (tokens ? { ...tokens } : null),
    saveTokens: async (t) => {
      tokens = { ...t };
    },
    clearTokens: async () => {
      cleared = true;
      tokens = null;
    },
    fetchImpl,
  };
  return {
    deps,
    calls,
    cleared: () => cleared,
    refreshToken: () => tokens?.refresh_token ?? null,
  };
}

const was401 = (call: Call) =>
  jsonResponse(
    {
      success: false,
      error: { code: "UNAUTHORIZED", message: "expired" },
    },
    401,
  );

test("expired access token triggers one refresh and retries with the new token", async () => {
  const h = makeDeps((call) => {
    if (call.url.includes("/auth/refresh")) {
      return jsonResponse({
        success: true,
        data: { access_token: "AT-2", refresh_token: "RT-2" },
      });
    }
    return call.auth === "Bearer AT-2"
      ? jsonResponse({ success: true, data: { me: true } })
      : was401(call);
  });

  const data = await requestCore<{ me: boolean }>(h.deps, "/auth/me");
  assert.equal(data.me, true);
  const refreshes = h.calls.filter((c) => c.url.includes("/auth/refresh"));
  assert.equal(refreshes.length, 1);
  assert.equal(h.refreshToken(), "RT-2"); // rotated tokens were saved
  const retry = h.calls.at(-1);
  assert.equal(retry?.auth, "Bearer AT-2");
});

test("concurrent 401s share a single refresh (single-flight)", async () => {
  const h = makeDeps((call) => {
    if (call.url.includes("/auth/refresh")) {
      return jsonResponse({
        success: true,
        data: { access_token: "AT-2", refresh_token: "RT-2" },
      });
    }
    return call.auth === "Bearer AT-2"
      ? jsonResponse({ success: true, data: { n: 1 } })
      : was401(call);
  });

  // Two GPS ticks racing after expiry: without single-flight the second
  // refresh would use the rotated-away token and log the driver out.
  const [a, b] = await Promise.allSettled([
    requestCore(h.deps, "/emergencies/s1/gps"),
    requestCore(h.deps, "/emergencies/s1/gps"),
  ]);
  assert.equal(a.status, "fulfilled");
  assert.equal(b.status, "fulfilled");
  const refreshes = h.calls.filter((c) => c.url.includes("/auth/refresh"));
  assert.equal(refreshes.length, 1);
  assert.equal(h.cleared(), false);
});

test("explicitly rejected refresh clears tokens and raises UNAUTHORIZED", async () => {
  const h = makeDeps((call) =>
    call.url.includes("/auth/refresh") ? jsonResponse({}, 401) : was401(call),
  );

  await assert.rejects(
    requestCore(h.deps, "/auth/me"),
    (e: unknown) => e instanceof ApiError && e.code === "UNAUTHORIZED",
  );
  assert.equal(h.cleared(), true);
});

test("network failure during refresh keeps tokens and raises NETWORK_ERROR", async () => {
  const h = makeDeps((call) => was401(call), { failRefreshTransport: true });

  await assert.rejects(
    requestCore(h.deps, "/auth/me"),
    (e: unknown) => e instanceof ApiError && e.code === "NETWORK_ERROR",
  );
  // A transient blip must NOT wipe valid tokens (old behavior logged out).
  assert.equal(h.cleared(), false);
  assert.equal(h.refreshToken(), "RT-1");
});

// ---- backend session-id lifecycle -------------------------------------------

function withFetch(
  impl: typeof fetch,
  run: () => Promise<void>,
): Promise<void> {
  const real = globalThis.fetch;
  globalThis.fetch = impl;
  return run().finally(() => {
    globalThis.fetch = real;
  });
}

test("stopActiveBackendSession is a no-op with no tracked session", async () => {
  // must run before any retrack: module state persists across tests
  await stopActiveBackendSession();
  assert.equal(__getActiveBackendSessionId(), null);
});

test("successful backendStop clears the tracked session id", async () => {
  await withFetch(
    (async (input) => {
      const url = String(input);
      if (url.endsWith("/emergencies/S-1/stop")) {
        return jsonResponse({ success: true, data: { status: "COMPLETED" } });
      }
      throw new TypeError(`unexpected call ${url}`);
    }) as typeof fetch,
    async () => {
      retrackBackendSession("S-1");
      assert.equal(__getActiveBackendSessionId(), "S-1");
      const res = await backendStop("S-1");
      assert.equal(res.status, "COMPLETED");
      assert.equal(__getActiveBackendSessionId(), null);
    },
  );
});

test("failed stop keeps the session id tracked so cleanup can retry", async () => {
  await withFetch(
    (async () => {
      throw new TypeError("simulated network failure");
    }) as typeof fetch,
    async () => {
      retrackBackendSession("S-2");
      await stopActiveBackendSession(); // must resolve despite the failure
      assert.equal(__getActiveBackendSessionId(), "S-2");
    },
  );
});

test("backend GPS sends the device capture timestamp", async () => {
  let requestBody: Record<string, unknown> | undefined;
  await withFetch(
    (async (_input, init) => {
      requestBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return jsonResponse({
        success: true,
        data: { nearby: [], command: null, status: "ACTIVE" },
      });
    }) as typeof fetch,
    async () => {
      const capturedAt = 1_700_000_000_000;
      await backendGps("S-3", {
        latitude: 12.9,
        longitude: 77.5,
        timestamp: capturedAt,
      });
    },
  );
  assert.equal(
    requestBody?.timestamp,
    new Date(1_700_000_000_000).toISOString(),
  );
});
