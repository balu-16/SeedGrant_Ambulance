import type { AppState } from "../types/models";
const object = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string" && v.length > 0;
// Identity fields start blank and fill from the backend — any string is valid.
const anyText = (v: unknown): v is string => typeof v === "string";
const number = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v) && v >= 0;
function location(v: unknown): boolean {
  if (!object(v) || !object(v.junction)) return false;
  return (
    typeof v.latitude === "number" &&
    Number.isFinite(v.latitude) &&
    Math.abs(v.latitude) <= 90 &&
    typeof v.longitude === "number" &&
    Number.isFinite(v.longitude) &&
    Math.abs(v.longitude) <= 180 &&
    text(v.area) &&
    anyText(v.road) &&
    anyText(v.junction.id) &&
    anyText(v.junction.name) &&
    ["East", "North", "West", "South"].includes(String(v.junction.approach))
  );
}
function emergency(v: unknown, status: "active" | "completed"): boolean {
  if (!object(v) || !Array.isArray(v.events)) return false;
  return (
    text(v.id) &&
    number(v.startedAt) &&
    anyText(v.hospital) &&
    number(v.distanceKm) &&
    v.status === status &&
    number(v.junctionsCrossed) &&
    Number.isInteger(v.junctionsCrossed) &&
    location(v.location) &&
    ["standby", "requested", "granted", "released"].includes(
      String(v.priority),
    ) &&
    (status === "active" || (number(v.endedAt) && v.endedAt >= v.startedAt)) &&
    v.events.every(
      (e) =>
        object(e) &&
        text(e.id) &&
        number(e.timestamp) &&
        [
          "started",
          "requested",
          "granted",
          "released",
          "crossed",
          "ended",
        ].includes(String(e.kind)) &&
        (e.junction === undefined || text(e.junction)) &&
        (e.approach === undefined || anyText(e.approach)),
    )
  );
}
/** Validate the complete persisted boundary before a screen accesses saved fields. */
export function decodeState(raw: string): AppState {
  const v: unknown = JSON.parse(raw);
  if (
    !object(v) ||
    v.version !== 1 ||
    typeof v.onboardingComplete !== "boolean" ||
    !object(v.driver) ||
    !object(v.ambulance) ||
    !object(v.settings) ||
    !Array.isArray(v.history)
  )
    throw new Error("Invalid saved data");
  const driver = v.driver;
  const ambulance = v.ambulance;
  const valid =
    ["id", "name", "email", "phone", "region"].every((k) =>
      anyText(driver[k]),
    ) &&
    typeof driver.onDuty === "boolean" &&
    ["id", "vehicleNumber", "hospital", "controlCenter"].every((k) =>
      anyText(ambulance[k]),
    ) &&
    typeof v.settings.reducedMotion === "boolean" &&
    typeof v.settings.confirmEmergency === "boolean" &&
    (v.auth === null ||
      (object(v.auth) && text(v.auth.driverId) && number(v.auth.signedInAt))) &&
    (v.active === null || (v.auth !== null && emergency(v.active, "active"))) &&
    v.history.every((s) => emergency(s, "completed"));
  if (!valid) throw new Error("Invalid saved data");
  return v as unknown as AppState;
}
