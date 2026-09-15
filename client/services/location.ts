/**
 * Live device GPS (expo-location, foreground only).
 *
 * Requests foreground permission and streams high-accuracy fixes roughly
 * every 3s / 5m — matching the emergency tick cadence. When permission is
 * denied, the device has no GPS (web/emulator), or the module is
 * unavailable, callers get `null` and must show the waiting state instead of the
 * route so the app and e2e keep working everywhere.
 */

import * as Location from "expo-location";

export interface GpsFix {
  latitude: number;
  longitude: number;
  accuracy: number | null;
  speed: number | null;
  heading: number | null;
  /** Device capture time from Expo, not the time the request was sent. */
  timestamp: number;
}

export type GpsStatus = "live" | "unavailable";

/** Ask for foreground location permission (false on web/denied). */
export async function requestGpsPermission(): Promise<boolean> {
  try {
    const current = await Location.getForegroundPermissionsAsync();
    if (current.granted) return true;
    const requested = await Location.requestForegroundPermissionsAsync();
    return requested.granted;
  } catch {
    return false;
  }
}

export interface GpsWatch {
  status: GpsStatus;
  fix: GpsFix | null;
  stop: () => void;
}

/**
 * Start watching the device position. Invokes `onFix` for every fix and
 * returns the latest fix accessor + stop handle. Never throws.
 */
export async function watchGps(
  onFix: (fix: GpsFix) => void,
): Promise<GpsWatch> {
  const noop = {
    status: "unavailable" as GpsStatus,
    fix: null,
    stop: () => undefined,
  };
  try {
    if (!(await requestGpsPermission())) return noop;
    let latest: GpsFix | null = null;
    const sub = await Location.watchPositionAsync(
      {
        accuracy: Location.Accuracy.High,
        timeInterval: 3000,
        distanceInterval: 5,
      },
      (pos) => {
        latest = {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy ?? null,
          speed: pos.coords.speed ?? null,
          heading: pos.coords.heading ?? null,
          timestamp: pos.timestamp,
        };
        onFix(latest);
      },
    );
    return {
      status: "live",
      get fix() {
        return latest;
      },
      stop: () => sub.remove(),
    };
  } catch {
    return noop;
  }
}
