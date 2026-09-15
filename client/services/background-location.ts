/**
 * Background GPS: TaskManager + startLocationUpdatesAsync with a
 * foreground-service notification (Android) and an outbox queue.
 *
 * Foreground watch stays in location.ts. This module is the background path:
 *  - requestBackgroundPermissionsAsync (Always) after foreground grant
 *  - startLocationUpdatesAsync(BG_TASK, {1-2s / 3-10m, High, foregroundService})
 *  - task posts each fix to the active backend session; on failure it is
 *    appended to an AsyncStorage outbox and retried (flushOutbox).
 *  - duplicate/replay safe: server treats same coords+timestamp<1s as no-op.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Location from "expo-location";
import * as TaskManager from "expo-task-manager";
import { backendGps } from "./emergency";
import { ApiError } from "./api";

export const BG_LOCATION_TASK = "ambulance-bg-location";
export const GPS_OUTBOX_KEY = "ambulance-driver:gps-outbox:v1";
const GPS_ACTIVE_SESSION_KEY = "ambulance-driver:gps-active-session:v1";
const MAX_OUTBOX = 200;
const MAX_QUEUED_AGE_MS = 10 * 60 * 1000;

export interface QueuedFix {
  sessionId: string;
  latitude: number;
  longitude: number;
  accuracy: number | null;
  speed: number | null;
  heading: number | null;
  timestamp: number;
}

let activeSessionId: string | null = null;
let taskDefined = false;
let outboxWrite: Promise<void> = Promise.resolve();

function defineTaskOnce(): void {
  if (taskDefined) return;
  taskDefined = true;
  TaskManager.defineTask<{ locations?: Location.LocationObject[] }>(
    BG_LOCATION_TASK,
    async ({ data, error }) => {
      if (error || !data?.locations?.length) return;
      const sessionId =
        activeSessionId ?? (await AsyncStorage.getItem(GPS_ACTIVE_SESSION_KEY));
      if (!sessionId) return;
      for (const loc of data.locations) {
        const fix: QueuedFix = {
          sessionId,
          latitude: loc.coords.latitude,
          longitude: loc.coords.longitude,
          accuracy: loc.coords.accuracy ?? null,
          speed: loc.coords.speed ?? null,
          heading: loc.coords.heading ?? null,
          timestamp: loc.timestamp,
        };
        try {
          await backendGps(sessionId, fix);
        } catch {
          await enqueueFix(fix);
        }
      }
      await flushOutbox().catch(() => undefined);
    },
  );
}

export async function requestBackgroundPermission(): Promise<boolean> {
  try {
    const cur = await Location.getBackgroundPermissionsAsync();
    if (cur.granted) return true;
    const req = await Location.requestBackgroundPermissionsAsync();
    return req.granted;
  } catch {
    return false;
  }
}

async function readOutbox(): Promise<QueuedFix[]> {
  try {
    const raw = await AsyncStorage.getItem(GPS_OUTBOX_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw) as QueuedFix[];
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

export async function enqueueFix(fix: QueuedFix): Promise<void> {
  outboxWrite = outboxWrite
    .catch(() => undefined)
    .then(async () => {
      try {
        const box = await readOutbox();
        box.push(fix);
        await AsyncStorage.setItem(
          GPS_OUTBOX_KEY,
          JSON.stringify(box.slice(-MAX_OUTBOX)),
        );
      } catch {
        /* storage unavailable — drop, next live fix continues */
      }
    });
  await outboxWrite;
}

/** Retry queued fixes in order; keeps failures for the next flush. */
export async function flushOutbox(): Promise<{
  sent: number;
  pending: number;
}> {
  const box = await readOutbox();
  if (box.length === 0) return { sent: 0, pending: 0 };
  const remaining: QueuedFix[] = [];
  let sent = 0;
  for (const fix of box) {
    // The API intentionally rejects stale capture times. Drop these locally
    // instead of retrying them forever after a long offline period.
    if (
      !Number.isFinite(fix.timestamp) ||
      Date.now() - fix.timestamp > MAX_QUEUED_AGE_MS
    ) {
      continue;
    }
    try {
      await backendGps(fix.sessionId, fix);
      sent += 1;
    } catch (error) {
      // A finished session, invalid fix, or unauthorized session cannot be
      // repaired by retrying; only transport failures remain queued.
      if (
        !(error instanceof ApiError) ||
        error.status === 0 ||
        error.status >= 500
      ) {
        remaining.push(fix);
      }
    }
  }
  await AsyncStorage.setItem(GPS_OUTBOX_KEY, JSON.stringify(remaining)).catch(
    () => undefined,
  );
  return { sent, pending: remaining.length };
}

export async function outboxLength(): Promise<number> {
  return (await readOutbox()).length;
}

/**
 * Start background updates for a session. Returns "started" | "foreground-only"
 * (background denied — caller keeps the foreground watch) | "unavailable".
 */
export async function startBackgroundTracking(
  sessionId: string,
): Promise<"started" | "foreground-only" | "unavailable"> {
  try {
    defineTaskOnce();
    activeSessionId = sessionId;
    await AsyncStorage.setItem(GPS_ACTIVE_SESSION_KEY, sessionId);
    const fg = await Location.getForegroundPermissionsAsync();
    if (!fg.granted) return "unavailable";
    const bg = await requestBackgroundPermission();
    if (!bg) return "foreground-only";
    const started = await TaskManager.isTaskRegisteredAsync(BG_LOCATION_TASK);
    if (!started) {
      await Location.startLocationUpdatesAsync(BG_LOCATION_TASK, {
        accuracy: Location.Accuracy.High,
        timeInterval: 2000,
        distanceInterval: 5,
        showsBackgroundLocationIndicator: true,
        foregroundService: {
          notificationTitle: "Emergency tracking active",
          notificationBody: "Sharing live location with traffic control.",
          notificationColor: "#E4232D",
        },
      });
    }
    await flushOutbox().catch(() => undefined);
    return "started";
  } catch {
    return "unavailable";
  }
}

export async function stopBackgroundTracking(): Promise<void> {
  activeSessionId = null;
  await AsyncStorage.removeItem(GPS_ACTIVE_SESSION_KEY).catch(() => undefined);
  try {
    const registered =
      await TaskManager.isTaskRegisteredAsync(BG_LOCATION_TASK);
    if (registered) await Location.stopLocationUpdatesAsync(BG_LOCATION_TASK);
  } catch {
    /* best effort */
  }
}

/** Test seam: which session the background task is feeding. */
export function __getBackgroundSessionId(): string | null {
  return activeSessionId;
}
