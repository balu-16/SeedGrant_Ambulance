/**
 * Pure helpers shared by the UI kit (kept out of ui.tsx so fast refresh sees
 * one component export per file).
 */

/** Badge tones — light token background + solid token text color. */
export type BadgeTone = "green" | "purple" | "red" | "blue" | "neutral";

/** Status → tone mapping shared with the app (plan §3): granted=green,
 *  requested=purple, active emergency/offline/expired=red, in-flight=blue,
 *  released/ready/idle=neutral. */
export function statusTone(status: string): BadgeTone {
  const s = status.toUpperCase();
  if (
    ["GRANTED", "COMPLETED", "ONLINE", "ACKNOWLEDGED", "ACTIVE", "ON_DUTY"].includes(
      s,
    )
  ) {
    return "green";
  }
  if (["PRIORITY_REQUESTED", "REQUESTED", "PENDING", "CROSSING"].includes(s)) {
    return "purple";
  }
  if (
    ["EMERGENCY_ACTIVE", "OFFLINE", "EXPIRED", "FAILED", "CANCELLED"].includes(s)
  ) {
    return "red";
  }
  if (["SENT", "IN_PROGRESS", "EN_ROUTE"].includes(s)) {
    return "blue";
  }
  return "neutral";
}

/** Initials for avatar circles ("Ravi Kumar" → "RK", "ops@h.org" → "OP"). */
export function initialsOf(name: string): string {
  const clean = name.trim();
  if (!clean) return "?";
  if (clean.includes("@")) {
    return clean.slice(0, 2).toUpperCase();
  }
  const parts = clean.split(/\s+/);
  const letters = parts.slice(0, 2).map((p) => p.charAt(0));
  return (letters.join("") || clean.slice(0, 2)).toUpperCase();
}
