/**
 * Pure display helpers for the HOSPITAL / POLICE pages (dates, durations,
 * severity/status → tone mappings shared by badges and timelines).
 */

import { statusTone, type BadgeTone } from "@/components/helpers";
import type { TimelineItem } from "@/components/ui";

const DASH = "—";

/** Bengaluru center — fallback when a junction has no coordinates. */
export const DEFAULT_CENTER: [number, number] = [12.9716, 77.5946];

/** Centralized tile URL (single source — VITE_TILES_URL or OSM default). */
export function tileUrl(): string {
  return (
    (import.meta as unknown as { env?: Record<string, string> }).env
      ?.VITE_TILES_URL ?? "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
  );
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? DASH
    : date.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

/** "just now" / "5m ago" / "3h ago" / "2d ago" (— for null). */
export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return DASH;
  if (ms < 45_000) return "just now";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/** Elapsed/duration text between two ISO stamps ("4m 32s", "1h 05m"). */
export function fmtElapsed(
  startIso: string | null | undefined,
  endIso?: string | null,
): string {
  if (!startIso) return DASH;
  const start = new Date(startIso).getTime();
  if (Number.isNaN(start)) return DASH;
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  if (Number.isNaN(end)) return DASH;
  const totalSeconds = Math.max(0, Math.floor((end - start) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  if (minutes > 0) return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  return `${seconds}s`;
}

/** Minutes between start/end (null when unknown — used for CSV/averages). */
export function durationMinutes(
  startIso: string | null | undefined,
  endIso: string | null | undefined,
): number | null {
  if (!startIso || !endIso) return null;
  const ms = new Date(endIso).getTime() - new Date(startIso).getTime();
  return Number.isNaN(ms) ? null : Math.round((ms / 60_000) * 10) / 10;
}

/** Alert severity → Badge tone (plan §4.2 Alerts feed). The backend emits
 * "warning" | "critical" — anything else falls through to neutral. */
export function severityTone(severity: string): BadgeTone {
  if (severity === "critical") return "red";
  if (severity === "warning") return "purple";
  return "neutral";
}

/** Badge tone color, for map dot fills and bar charts. */
export function toneColor(tone: BadgeTone): string {
  switch (tone) {
    case "green":
      return "var(--green)";
    case "red":
      return "var(--red)";
    case "purple":
      return "var(--purple)";
    case "blue":
      return "var(--blue)";
    default:
      return "var(--muted)";
  }
}

/** Status string → Badge tone (ui kit mapping). */
export function statusBadgeTone(status: string): BadgeTone {
  return statusTone(status);
}

/** Status → Timeline dot tone (purple renders as blue on the timeline rail). */
export function timelineTone(status: string): TimelineItem["tone"] {
  const tone = statusTone(status);
  return tone === "purple" ? "blue" : tone;
}
