import type {
  AppState,
  Driver,
  Ambulance,
  MockSession,
  PriorityEvent,
  Settings,
  EmergencySession,
} from "../types/models";
import { EMPTY_LOCATION } from "../services/defaultState";
export type Action =
  | { type: "hydrate"; state: AppState }
  | { type: "onboard" }
  | { type: "login"; auth: MockSession }
  | { type: "linkBackend"; sessionId: string }
  | {
      type: "start";
      now: number;
      seed?: { latitude: number; longitude: number };
      backendSessionId?: string;
    }
  | { type: "sessionEvent"; event: PriorityEvent }
  | {
      type: "liveFix";
      now: number;
      latitude: number;
      longitude: number;
      accuracy?: number | null;
      speed?: number | null;
    }
  | {
      type: "stop";
      now: number;
      status?: "completed" | "cancelled" | "timed_out";
    }
  | { type: "logout"; now: number }
  | { type: "driver"; patch: Partial<Omit<Driver, "id">> }
  | { type: "ambulance"; patch: Partial<Omit<Ambulance, "id">> }
  | { type: "settings"; patch: Partial<Settings> };
function stop(
  state: AppState,
  now: number,
  status: "completed" | "cancelled" | "timed_out" = "completed",
): AppState {
  if (!state.active) return state;
  const s = state.active;
  const release = s.priority === "requested" || s.priority === "granted";
  const junctionName = s.location.junction.name;
  const completed: EmergencySession = {
    ...s,
    status,
    endedAt: now,
    priority: "released",
    events: [
      ...s.events,
      ...(release
        ? [
            {
              id: `${s.id}-final-release`,
              kind: "released" as const,
              timestamp: now,
              ...(junctionName ? { junction: junctionName } : {}),
            },
          ]
        : []),
      { id: `${s.id}-end`, kind: "ended", timestamp: now },
    ],
  };
  return { ...state, active: null, history: [completed, ...state.history] };
}
/** Haversine distance in km between two fixes. */
function haversineKm(
  aLat: number,
  aLon: number,
  bLat: number,
  bLon: number,
): number {
  const R = 6371;
  const dLat = ((bLat - aLat) * Math.PI) / 180;
  const dLon = ((bLon - aLon) * Math.PI) / 180;
  const la1 = (aLat * Math.PI) / 180;
  const la2 = (bLat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}
export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "hydrate":
      return action.state;
    case "onboard":
      return { ...state, onboardingComplete: true };
    case "login":
      return { ...state, auth: action.auth, onboardingComplete: true };
    case "linkBackend":
      return state.active
        ? {
            ...state,
            active: { ...state.active, backendSessionId: action.sessionId },
          }
        : state;
    case "start":
      return !state.auth || state.active
        ? state
        : {
            ...state,
            active: {
              id: `emergency-${action.now}`,
              ...(action.backendSessionId
                ? { backendSessionId: action.backendSessionId }
                : {}),
              startedAt: action.now,
              hospital: state.ambulance.hospital,
              distanceKm: 0,
              status: "active",
              junctionsCrossed: 0,
              priority: "standby",
              location:
                action.seed &&
                Number.isFinite(action.seed.latitude) &&
                Number.isFinite(action.seed.longitude)
                  ? {
                      ...EMPTY_LOCATION,
                      latitude: action.seed.latitude,
                      longitude: action.seed.longitude,
                      area: "Live GPS fix",
                    }
                  : EMPTY_LOCATION,
              events: [
                {
                  id: `start-${action.now}`,
                  kind: "started",
                  timestamp: action.now,
                },
              ],
            },
          };
    case "sessionEvent": {
      if (!state.active) return state;
      // Backend command truth also drives the priority state: the card and
      // the stop-release logic read it, and nothing else may invent it.
      const priority =
        action.event.kind === "requested"
          ? "requested"
          : action.event.kind === "granted"
            ? "granted"
            : action.event.kind === "released"
              ? "released"
              : state.active.priority;
      return {
        ...state,
        active: {
          ...state.active,
          priority,
          events: [...state.active.events, action.event],
        },
      };
    }
    case "liveFix": {
      if (!state.active) return state;
      const prev = state.active.location;
      // The very first fix arrives from the (0,0) empty snapshot — it starts
      // the distance at 0 instead of adding a bogus intercontinental step.
      const firstFix = prev.latitude === 0 && prev.longitude === 0;
      const stepKm = haversineKm(
        prev.latitude,
        prev.longitude,
        action.latitude,
        action.longitude,
      );
      // Ignore teleport jumps (>2km in one fix) — bad GPS, not driving.
      const validStep =
        firstFix || !Number.isFinite(stepKm) || stepKm >= 2 ? 0 : stepKm;
      return {
        ...state,
        active: {
          ...state.active,
          distanceKm:
            Math.round((state.active.distanceKm + validStep) * 100) / 100,
          location: {
            ...prev,
            latitude: action.latitude,
            longitude: action.longitude,
            area: "Live GPS fix",
          },
        },
      };
    }
    case "stop":
      return stop(state, action.now, action.status);
    case "logout":
      return { ...stop(state, action.now), auth: null };
    case "driver":
      return {
        ...state,
        driver: { ...state.driver, ...action.patch, id: state.driver.id },
      };
    case "ambulance":
      return {
        ...state,
        ambulance: {
          ...state.ambulance,
          ...action.patch,
          id: state.ambulance.id,
        },
      };
    case "settings":
      return { ...state, settings: { ...state.settings, ...action.patch } };
  }
}
export function launchRoute(
  state: AppState,
): "/home" | "/login" | "/onboarding" {
  return state.auth
    ? "/home"
    : state.onboardingComplete
      ? "/login"
      : "/onboarding";
}
