/**
 * ADMIN pages — pure formatting/validation helpers. No React here so fast
 * refresh always sees component-only modules (lint: only-export-components).
 */

import type { BadgeTone } from "@/components/helpers";
import { statusTone } from "@/components/helpers";

/** Best-effort human message from an unknown thrown value (ApiError etc). */
export function errMsg(e: unknown): string {
  if (e instanceof Error && e.message) return e.message;
  return "Something went wrong — please try again.";
}

/** ISO timestamp → local date + time, "—" when missing/invalid. */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

/** ISO timestamp → local date, "—" when missing/invalid. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString();
}

/** Relative age for heartbeats/GPS fixes ("4m ago"). */
export function fmtAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m ago`;
  return `${Math.floor(h / 24)}d ${h % 24}h ago`;
}

/** Emergency duration started→ended ("12m", "1h 05m"); null when unknown. */
export function fmtDuration(
  startIso: string | null,
  endIso: string | null,
): string | null {
  if (!startIso) return null;
  const a = new Date(startIso).getTime();
  const b = endIso ? new Date(endIso).getTime() : Number.NaN;
  if (Number.isNaN(a) || Number.isNaN(b) || b < a) return null;
  const mins = Math.max(0, Math.round((b - a) / 60000));
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, "0")}m`;
}

/** Portal role → badge tone. */
export function roleTone(role: string): BadgeTone {
  if (role === "ADMIN") return "purple";
  if (role === "HOSPITAL") return "green";
  if (role === "POLICE") return "blue";
  return "neutral";
}

/** Status → Timeline dot tone (the Timeline palette has no purple). */
export function timelineTone(
  status: string,
): "green" | "red" | "blue" | "neutral" {
  const tone = statusTone(status);
  if (tone === "green" || tone === "red" || tone === "neutral") return tone;
  return "blue";
}

/** Readable random password (no look-alike characters), crypto-backed. */
export function generatePassword(length = 14): string {
  const alphabet =
    "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%&*";
  const bytes = new Uint32Array(length);
  crypto.getRandomValues(bytes);
  let out = "";
  for (let i = 0; i < length; i += 1) {
    out += alphabet[bytes[i] % alphabet.length];
  }
  return out;
}

/** Render an unknown config-check / sweep value for display. */
export function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v === "" ? "—" : v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

/** Shorten a UUID-ish id for labels ("3f9c2ab1-…" → "3f9c2ab1…"). */
export function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}
