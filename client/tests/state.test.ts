import { test } from "node:test";
import assert from "node:assert/strict";
import { initialState, EMPTY_LOCATION } from "../services/defaultState";
import { authService } from "../services/auth";
import { reducer, launchRoute } from "../store/reducer";
import { filterHistory } from "../utils/history";
import { decodeState } from "../utils/persistence";
import { mapHistoryItem } from "../services/emergency";
import type { EmergencySession } from "../types/models";
const now = new Date(2026, 8, 12, 16, 0).getTime();
const loggedIn = () =>
  reducer(initialState(), {
    type: "login",
    auth: { driverId: "real-user-id", signedInAt: now },
  });

function session(
  overrides: Partial<EmergencySession>,
  i = 0,
): EmergencySession {
  return {
    id: `hist-${i}`,
    startedAt: now - (i + 1) * 86_400_000,
    endedAt: now - (i + 1) * 86_400_000 + 600_000,
    hospital: "Test Hospital",
    distanceKm: 3,
    status: "completed",
    junctionsCrossed: 2,
    events: [],
    priority: "released",
    location: EMPTY_LOCATION,
    ...overrides,
  };
}
test("launch restores onboarding, login, and authenticated navigation", () => {
  const first = initialState();
  assert.equal(launchRoute(first), "/onboarding");
  const onboarded = reducer(first, { type: "onboard" });
  assert.equal(launchRoute(onboarded), "/login");
  assert.equal(launchRoute(loggedIn()), "/home");
  assert.equal(
    launchRoute(reducer(loggedIn(), { type: "logout", now })),
    "/login",
  );
});
test("initial state has no fabricated identity, history, or demo data", () => {
  const s = initialState();
  assert.equal(s.auth, null);
  assert.equal(s.history.length, 0);
  assert.equal(s.driver.id, "");
  assert.equal(s.ambulance.vehicleNumber, "");
  assert.equal(JSON.stringify(s).includes("Bandra"), false);
  assert.equal(JSON.stringify(s).includes("DRV-1024"), false);
});
test("signIn without a configured backend explains the missing URL", async () => {
  // EXPO_PUBLIC_API_URL is unset in node tests → api disabled.
  await assert.rejects(
    authService.signIn("driver001", "123456"),
    /not configured/,
  );
});
test("start requires authentication and is idempotent while active", () => {
  const first = initialState();
  assert.equal(reducer(first, { type: "start", now }), first);
  const started = reducer(loggedIn(), { type: "start", now });
  assert.equal(started.active?.events.length, 1);
  assert.equal(reducer(started, { type: "start", now: now + 1 }), started);
  // starts with no fabricated location: the empty snapshot until a fix lands
  assert.equal(started.active?.location.latitude, 0);
});
test("session events come from the backend command stream, not a simulator", () => {
  let state = reducer(loggedIn(), { type: "start", now });
  state = reducer(state, {
    type: "sessionEvent",
    event: {
      id: "c1",
      kind: "requested",
      timestamp: now + 3000,
      approach: "NORTH",
    },
  });
  state = reducer(state, {
    type: "sessionEvent",
    event: { id: "c1-ack", kind: "granted", timestamp: now + 4000 },
  });
  assert.deepEqual(
    state.active?.events.map((e) => e.kind),
    ["started", "requested", "granted"],
  );
  // unknown junction placeholders never appear in events
  assert.equal(state.active?.junctionsCrossed, 0);
});
test("live fixes accumulate real distance and reject teleports", () => {
  let state = reducer(loggedIn(), { type: "start", now });
  // first fix: starts distance at 0 even though the empty snapshot is (0,0)
  state = reducer(state, {
    type: "liveFix",
    now: now + 1000,
    latitude: 12.9716,
    longitude: 77.5946,
  });
  assert.equal(state.active?.location.area, "Live GPS fix");
  assert.equal(state.active?.distanceKm, 0);
  // a real ~1km step accumulates
  state = reducer(state, {
    type: "liveFix",
    now: now + 2000,
    latitude: 12.9805,
    longitude: 77.5946,
  });
  assert.ok((state.active?.distanceKm ?? 0) > 0.9);
  // a >2km jump in one fix is ignored
  state = reducer(state, {
    type: "liveFix",
    now: now + 3000,
    latitude: 13.1,
    longitude: 77.5946,
  });
  const before = state.active?.distanceKm ?? 0;
  assert.equal(state.active?.distanceKm, before);
});
test("stop releases outstanding priority and records a completed session once", () => {
  let state = reducer(loggedIn(), { type: "start", now });
  state = reducer(state, {
    type: "sessionEvent",
    event: { id: "c1", kind: "requested", timestamp: now + 3000 },
  });
  state = reducer(state, { type: "stop", now: now + 10000 });
  assert.equal(state.active, null);
  assert.equal(state.history.length, 1);
  assert.deepEqual(
    state.history[0].events.slice(-2).map((e) => e.kind),
    ["released", "ended"],
  );
  assert.equal(state.history[0].endedAt, now + 10000);
  assert.equal(state.history[0].status, "completed");
  assert.equal(reducer(state, { type: "stop", now: now + 10001 }), state);
});
test("logout ends active emergency and preserves onboarding and history", () => {
  const state = reducer(reducer(loggedIn(), { type: "start", now }), {
    type: "logout",
    now: now + 30000,
  });
  assert.equal(state.auth, null);
  assert.equal(state.active, null);
  assert.equal(state.history.length, 1);
  assert.ok(state.onboardingComplete);
});
test("local edits patch mutable fields but never fabricate ids", () => {
  let state = reducer(loggedIn(), {
    type: "driver",
    patch: { name: "Real Driver", phone: "+91 90000 00000" },
  });
  state = reducer(state, {
    type: "ambulance",
    patch: { hospital: "Real Hospital" },
  });
  assert.equal(state.driver.id, "");
  assert.equal(state.ambulance.id, "");
  assert.equal(state.driver.name, "Real Driver");
  assert.equal(state.ambulance.hospital, "Real Hospital");
});
test("history filters by calendar periods and case-insensitive hospital search", () => {
  const history = [
    session(
      { hospital: "Alpha Hospital", startedAt: now - 3_600_000, endedAt: now },
      0,
    ),
    session({ hospital: "Beta Clinic" }, 1),
    session({ hospital: "Gamma Hospital" }, 2),
    session({ hospital: "Delta Clinic" }, 3),
  ];
  assert.equal(filterHistory(history, "All", "", "all", now).length, 4);
  assert.equal(filterHistory(history, "Today", "", "all", now).length, 1);
  assert.equal(
    filterHistory(history, "This Week", "", "completed", now).length,
    4,
  );
  assert.equal(
    filterHistory(history, "This Month", " BETA ", "all", now).length,
    1,
  );
  assert.equal(filterHistory(history, "All", "unknown", "all", now).length, 0);
});
test("backend history rows map to real sessions with events and distance", () => {
  const mapped = mapHistoryItem({
    id: "9d2f6a2e-1c3b-4a5d-8e7f-0a1b2c3d4e5f",
    status: "COMPLETED",
    hospital: "City Hospital",
    ended_reason: "COMPLETED",
    started_at: new Date(now - 900_000).toISOString(),
    ended_at: new Date(now).toISOString(),
    distance_m: 2840.5,
    junctions_crossed: 3,
    events: [
      {
        id: "e1",
        kind: "session",
        type: "started",
        at: new Date(now - 900_000).toISOString(),
      },
      {
        id: "e2",
        kind: "command",
        type: "PRIORITY_REQUEST",
        status: "ACKNOWLEDGED",
        approach: "NORTH",
        at: new Date(now - 800_000).toISOString(),
      },
      {
        id: "e3",
        kind: "command",
        type: "RELEASE_PRIORITY",
        at: new Date(now - 100_000).toISOString(),
      },
      {
        id: "e4",
        kind: "session",
        type: "COMPLETED",
        at: new Date(now).toISOString(),
      },
    ],
    last_latitude: 12.97,
    last_longitude: 77.59,
  });
  assert.equal(mapped.hospital, "City Hospital");
  assert.equal(mapped.distanceKm, 2.84);
  assert.equal(mapped.junctionsCrossed, 3);
  assert.equal(mapped.status, "completed");
  assert.deepEqual(
    mapped.events.map((e) => e.kind),
    ["started", "granted", "released", "ended"],
  );
  // rows without a usable fix keep unusable coordinates, never fabricated ones
  const noFix = mapHistoryItem({
    id: "9d2f6a2e-1c3b-4a5d-8e7f-0a1b2c3d4e5f",
    status: "TIMED_OUT",
    started_at: new Date(now - 900_000).toISOString(),
  });
  assert.equal(noFix.location.latitude, 0);
  assert.ok(noFix.location.area.startsWith("NO_FIX:"));
});
test("saved data round-trips, including an active session and local edits", () => {
  let state = reducer(loggedIn(), { type: "start", now });
  state = reducer(state, {
    type: "liveFix",
    now,
    latitude: 12.9716,
    longitude: 77.5946,
  });
  assert.deepEqual(decodeState(JSON.stringify(state)), state);
});
test("malformed and incompatible storage cannot enter application state", () => {
  assert.throws(() => decodeState("{broken"));
  assert.throws(() =>
    decodeState(JSON.stringify({ ...loggedIn(), version: 2 })),
  );
  assert.throws(() =>
    decodeState(JSON.stringify({ ...loggedIn(), driver: {} })),
  );
  const state = reducer(loggedIn(), { type: "start", now });
  assert.throws(() =>
    decodeState(
      JSON.stringify({ ...state, active: { ...state.active, location: null } }),
    ),
  );
  assert.throws(() => decodeState(JSON.stringify({ ...state, auth: null })));
});
