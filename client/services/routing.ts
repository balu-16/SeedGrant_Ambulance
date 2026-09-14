/**
 * Free routing: OSRM public API (no key) for polyline + ETA/distance.
 * Display tiles: Carto light (same look as admin) with OSM fallback.
 *
 * Env:
 *  EXPO_PUBLIC_OSRM_URL (default https://router.project-osrm.org)
 *  EXPO_PUBLIC_TILES_URL (default Carto light_all)
 */

export const DEFAULT_OSRM_URL = "https://router.project-osrm.org";
export const DEFAULT_TILES_URL =
  "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png";
export const OSM_FALLBACK_TILES_URL =
  "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

export function osrmBaseUrl(): string {
  const raw = (process.env.EXPO_PUBLIC_OSRM_URL ?? "").trim();
  return (raw.length > 0 ? raw : DEFAULT_OSRM_URL).replace(/\/+$/, "");
}

export function tilesUrl(): string {
  const raw = (process.env.EXPO_PUBLIC_TILES_URL ?? "").trim();
  return raw.length > 0 ? raw : DEFAULT_TILES_URL;
}

export interface LatLon {
  latitude: number;
  longitude: number;
}

export interface RouteResult {
  /** [lat, lon] pairs decoded from OSRM geojson. */
  polyline: LatLon[];
  distanceM: number;
  durationS: number;
}

function isUsableCoord(p: LatLon | null | undefined): p is LatLon {
  return (
    !!p &&
    Number.isFinite(p.latitude) &&
    Number.isFinite(p.longitude) &&
    !(p.latitude === 0 && p.longitude === 0)
  );
}

/**
 * Fetch a driving route from OSRM. Returns null on any failure so callers
 * fall back to straight-line display — never throws.
 */
export async function fetchRoute(
  from: LatLon,
  to: LatLon,
  signal?: AbortSignal,
): Promise<RouteResult | null> {
  if (!isUsableCoord(from) || !isUsableCoord(to)) return null;
  try {
    const url =
      `${osrmBaseUrl()}/route/v1/driving/` +
      `${from.longitude},${from.latitude};${to.longitude},${to.latitude}` +
      `?overview=full&geometries=geojson`;
    const res = await fetch(url, { signal });
    if (!res.ok) return null;
    const json = (await res.json()) as {
      routes?: {
        geometry?: { coordinates?: [number, number][] };
        distance?: number;
        duration?: number;
      }[];
    };
    const r = json.routes?.[0];
    if (!r) return null;
    const coords = r.geometry?.coordinates ?? [];
    return {
      polyline: coords
        .filter(
          (c): c is [number, number] =>
            Array.isArray(c) && Number.isFinite(c[0]) && Number.isFinite(c[1]),
        )
        .map(([lon, lat]) => ({ latitude: lat, longitude: lon })),
      distanceM: r.distance ?? 0,
      durationS: r.duration ?? 0,
    };
  } catch {
    return null;
  }
}

export function formatDistance(m: number | null | undefined): string {
  if (m == null || !Number.isFinite(m) || m <= 0) return "—";
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return "—";
  const min = Math.max(1, Math.round(seconds / 60));
  return min >= 60 ? `${Math.floor(min / 60)}h ${min % 60}m` : `${min} min`;
}
