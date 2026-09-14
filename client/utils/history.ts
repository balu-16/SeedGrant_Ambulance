import type { EmergencySession } from "../types/models";
export type Period = "All" | "Today" | "This Week" | "This Month";
export function filterHistory(
  sessions: EmergencySession[],
  period: Period,
  query: string,
  status: "all" | "completed",
  now = Date.now(),
) {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  if (period === "This Week")
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  if (period === "This Month") start.setDate(1);
  return sessions.filter(
    (s) =>
      (period === "All" || s.startedAt >= start.getTime()) &&
      s.startedAt <= now &&
      s.hospital.toLowerCase().includes(query.trim().toLowerCase()) &&
      (status === "all" || s.status === status),
  );
}
