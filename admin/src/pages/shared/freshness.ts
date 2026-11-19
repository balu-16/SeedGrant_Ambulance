/**
 * Freshness hooks + pure helpers (contract §5/§9): "Last updated Xs ago"
 * captions, the portal-stale banner threshold and the GPS-stale badge rule.
 * Thresholds come from GET /portal/status (staleTime 60s, polled once per
 * session) with sane defaults while the query loads or fails.
 */

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchPortalStatus } from "@/services/portal";

export const DEFAULT_FRESHNESS = {
  gps_stale_seconds: 30,
  portal_stale_seconds: 30,
  device_offline_seconds: 60,
};

/** GET /portal/status — polled once per session (staleTime 60s, no polling). */
export function usePortalStatus() {
  return useQuery({
    queryKey: ["portal", "status"],
    queryFn: fetchPortalStatus,
    staleTime: 60_000,
    refetchInterval: false,
    retry: false,
  });
}

/** Freshness thresholds with defaults when /portal/status is unavailable. */
export function useFreshnessThresholds(): {
  gpsStaleSeconds: number;
  portalStaleSeconds: number;
  deviceOfflineSeconds: number;
  simulation: boolean | null;
} {
  const q = usePortalStatus();
  const f = q.data?.freshness;
  return {
    gpsStaleSeconds: f?.gps_stale_seconds ?? DEFAULT_FRESHNESS.gps_stale_seconds,
    portalStaleSeconds:
      f?.portal_stale_seconds ?? DEFAULT_FRESHNESS.portal_stale_seconds,
    deviceOfflineSeconds:
      f?.device_offline_seconds ?? DEFAULT_FRESHNESS.device_offline_seconds,
    simulation: q.data ? q.data.simulation : null,
  };
}

/**
 * Age (seconds) of the last successful data update, re-rendered every second.
 * `updatedAt` is the React Query dataUpdatedAt of the observed query.
 */
export function useFreshness(
  updatedAt: number | undefined,
): { secondsAgo: number | null } {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (updatedAt === undefined) return { secondsAgo: null };
  return { secondsAgo: Math.max(0, Math.floor((now - updatedAt) / 1000)) };
}

/** True when the last successful refresh is older than `staleSeconds`. */
export function isStale(
  updatedAt: number | undefined,
  staleSeconds: number,
  now = Date.now(),
): boolean {
  if (updatedAt === undefined) return false;
  return now - updatedAt > staleSeconds * 1000;
}

/**
 * GPS-stale rule (contract §9): a fix older than gps_stale_seconds shows the
 * "Stale GPS" badge. No fix at all is "no GPS", not "stale GPS".
 */
export function isGpsStale(
  recordedAt: string | null | undefined,
  gpsStaleSeconds: number,
  now = Date.now(),
): boolean {
  if (!recordedAt) return false;
  const t = new Date(recordedAt).getTime();
  if (Number.isNaN(t)) return false;
  return now - t > gpsStaleSeconds * 1000;
}

/** Server-observed age in seconds (observed_at from /admin/live), or null. */
export function observedAgeSeconds(
  observedAt: string | null | undefined,
  now = Date.now(),
): number | null {
  if (!observedAt) return null;
  const t = new Date(observedAt).getTime();
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((now - t) / 1000));
}
