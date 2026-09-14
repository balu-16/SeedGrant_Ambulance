/**
 * Backend emergency-session API. All calls require a backend-linked login
 * (see api.ts) and go through its `request()` client so they inherit
 * refresh-on-401 and the shared error mapping.
 *
 * GPS fixes are posted from the app's live location while a session is
 * active; the backend runs the real geofence/priority engine on them.
 */

import type { EmergencySession, PriorityEvent } from "../types/models";

import { isBackendLinked, request } from "./api";

export { apiMyAmbulance } from "./api";

export interface BackendSession {
  session_id: string;
  status: string;
}

export interface NearbyJunction {
  junction_id: string;
  distance_m: number;
  approach: string;
  approaching: boolean;
}

export interface BackendGpsResult {
  nearby: NearbyJunction[];
  command: { id: string; type: string; approach: string } | null;
  status: string;
  duplicate?: boolean;
}

/** One timeline row from GET /emergencies/history (server-built). */
export interface BackendHistoryEvent {
  id: string;
  kind: "session" | "command";
  type: string;
  status?: string | null;
  junction_id?: string | null;
  approach?: string | null;
  at?: string | null;
}

export interface BackendHistoryItem {
  id: string;
  status: string;
  hospital?: string | null;
  ended_reason?: string | null;
  started_at: string;
  ended_at?: string | null;
  distance_m?: number | null;
  junctions_crossed?: number | null;
  events?: BackendHistoryEvent[] | null;
  last_latitude?: number | null;
  last_longitude?: number | null;
}

export interface BackendJunction {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
}

/** Junction catalog (driver-role allowed) for resolving nearby junction names. */
export async function backendJunctions(): Promise<BackendJunction[]> {
  return request<BackendJunction[]>("/junctions");
}

/**
 * Id of the backend emergency session this app is currently feeding, if any.
 * HomeScreen keeps the id in local state that ProfileScreen cannot see, so it
 * is tracked here as well: logout and unmount cleanup use it to end the
 * server-side session (set by backendStart()/backendCurrent(), cleared by
 * backendStop()).
 */
let activeBackendSessionId: string | null = null;

/**
 * Best-effort stop of the tracked backend session. Resolves even when the
 * stop request fails (the error is logged, never thrown) — the session id
 * stays tracked on failure so a later logout/unmount can retry.
 */
export async function stopActiveBackendSession(): Promise<void> {
  const sessionId = activeBackendSessionId;
  if (!sessionId) return;
  try {
    await backendStop(sessionId);
  } catch (e) {
    console.warn("[emergency] failed to stop backend emergency session:", e);
  }
}

/**
 * Re-track a session id after a failed stop attempt so cleanup paths
 * (logout, unmount) can retry ending the server-side session.
 */
export function retrackBackendSession(sessionId: string): void {
  activeBackendSessionId = sessionId;
}

/** Test seam: inspect the tracked session id (node unit tests only). */
export function __getActiveBackendSessionId(): string | null {
  return activeBackendSessionId;
}

export async function backendStart(
  ambulanceId: string,
  hospital?: string,
): Promise<BackendSession> {
  const body: Record<string, unknown> = { ambulance_id: ambulanceId };
  if (hospital) body.hospital = hospital;
  const session = await request<BackendSession>("/emergencies/start", {
    method: "POST",
    body,
  });
  activeBackendSessionId = session.session_id;
  return session;
}

export async function backendCurrent(): Promise<
  { active: false } | { active: boolean; session_id: string; status: string }
> {
  const current = await request<
    { active: false } | { active: boolean; session_id: string; status: string }
  >("/emergencies/current");
  activeBackendSessionId = current.active ? current.session_id : null;
  return current;
}

export async function backendStop(
  sessionId: string,
): Promise<{ status: string }> {
  const result = await request<{ status: string }>(
    `/emergencies/${sessionId}/stop`,
    { method: "POST" },
  );
  // Clear the tracker only once the server actually ended the session; a
  // failed stop must leave it tracked so cleanup paths can retry.
  if (activeBackendSessionId === sessionId) activeBackendSessionId = null;
  return result;
}

export interface GpsFixInput {
  latitude: number;
  longitude: number;
  accuracy?: number | null;
  speed?: number | null;
  heading?: number | null;
}

export async function backendGps(
  sessionId: string,
  fix: GpsFixInput,
): Promise<BackendGpsResult> {
  const body: Record<string, unknown> = {
    latitude: fix.latitude,
    longitude: fix.longitude,
  };
  if (fix.accuracy != null) body.accuracy = fix.accuracy;
  if (fix.speed != null && fix.speed >= 0) body.speed = fix.speed;
  if (fix.heading != null && fix.heading >= 0 && fix.heading <= 360) {
    body.heading = fix.heading;
  }
  return (await request<BackendGpsResult>(`/emergencies/${sessionId}/gps`, {
    method: "POST",
    body,
  })) as BackendGpsResult;
}

export async function backendHistory(params?: {
  limit?: number;
  offset?: number;
  status?: string;
  q?: string;
  from?: string;
  to?: string;
}): Promise<BackendHistoryItem[]> {
  const qs = new URLSearchParams();
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  if (params?.status) qs.set("status", params.status);
  if (params?.q) qs.set("q", params.q);
  if (params?.from) qs.set("from", params.from);
  if (params?.to) qs.set("to", params.to);
  const suffix = qs.size > 0 ? `?${qs.toString()}` : "";
  return request<BackendHistoryItem[]>(`/emergencies/history${suffix}`);
}

export async function backendHeartbeat(
  sessionId: string,
): Promise<{ status: string }> {
  return request<{ status: string }>(`/emergencies/${sessionId}/heartbeat`, {
    method: "POST",
  });
}

export interface BackendHospital {
  id: string;
  name: string;
  latitude?: number | null;
  longitude?: number | null;
}

export async function backendHospitals(): Promise<BackendHospital[]> {
  return request<BackendHospital[]>("/hospitals");
}

export async function backendPatient(
  sessionId: string,
  patch: { notes?: string; severity?: string },
): Promise<{ status: string }> {
  return request<{ status: string }>(`/emergencies/${sessionId}/patient`, {
    method: "POST",
    body: patch,
  });
}

/** Backend terminal statuses (server/app/core/consts.py). */
const TERMINAL_STATUSES = new Set(["COMPLETED", "CANCELLED", "TIMED_OUT"]);

/**
 * Map a backend history row onto the local EmergencySession shape.
 * Uses backend distance/junctions/events/last-fix when present. Rows without
 * a usable fix keep zero coordinates AND are flagged via the area prefix so
 * the UI can hide the map link instead of plotting (0,0).
 */
export function mapHistoryItem(item: BackendHistoryItem): EmergencySession {
  const startedAt = Date.parse(item.started_at) || Date.now();
  const parsedEndedAt = item.ended_at ? Date.parse(item.ended_at) : NaN;
  const terminal = TERMINAL_STATUSES.has(item.status);
  const hasFix =
    typeof item.last_latitude === "number" &&
    typeof item.last_longitude === "number" &&
    Number.isFinite(item.last_latitude) &&
    Number.isFinite(item.last_longitude) &&
    !(item.last_latitude === 0 && item.last_longitude === 0);
  const events: PriorityEvent[] = [];
  for (const e of item.events ?? []) {
    const timestamp = (e.at ? Date.parse(e.at) : NaN) || startedAt;
    if (e.kind === "session" && e.type === "started") {
      events.push({ id: e.id, kind: "started", timestamp });
    } else if (e.kind === "session") {
      events.push({ id: e.id, kind: "ended", timestamp });
    } else if (e.kind === "command") {
      if (e.type === "PRIORITY_REQUEST") {
        events.push({
          id: e.id,
          kind: e.status === "ACKNOWLEDGED" ? "granted" : "requested",
          timestamp,
          approach: e.approach ?? undefined,
        });
      } else if (e.type === "RELEASE_PRIORITY" || e.type === "FORCE_RELEASE") {
        events.push({ id: e.id, kind: "released", timestamp });
      }
    }
  }
  return {
    id: `backend-${item.id}`,
    startedAt,
    endedAt: terminal
      ? Number.isFinite(parsedEndedAt)
        ? parsedEndedAt
        : startedAt
      : undefined,
    hospital: item.hospital || "Unnamed hospital",
    distanceKm:
      typeof item.distance_m === "number" && Number.isFinite(item.distance_m)
        ? Math.round((item.distance_m / 1000) * 100) / 100
        : 0,
    status:
      item.status === "COMPLETED"
        ? "completed"
        : item.status === "CANCELLED" || item.status === "TIMED_OUT"
          ? "cancelled"
          : "active",
    junctionsCrossed:
      typeof item.junctions_crossed === "number" ? item.junctions_crossed : 0,
    events,
    priority: "released",
    location: hasFix
      ? {
          latitude: item.last_latitude as number,
          longitude: item.last_longitude as number,
          area: item.ended_reason || item.status,
          road: "",
          junction: { id: "", name: "", approach: "East" },
        }
      : {
          // No backend fix: keep unusable (0,0) coordinates but flag the area
          // so the UI hides the map link (never plot 0,0).
          latitude: 0,
          longitude: 0,
          area: `NO_FIX:${item.ended_reason || item.status}`,
          road: "",
          junction: { id: "", name: "", approach: "East" },
        },
  };
}

export { isBackendLinked };
