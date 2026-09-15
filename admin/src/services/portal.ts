/**
 * Portal endpoint functions (typed contracts in types/portal.ts, endpoint
 * contract in ADMIN_PORTAL_PLAN.md §5). Every function routes through
 * services/api.ts request<T>() — no fetch calls anywhere else.
 */

import { request } from "@/services/api";
import type {
  Ambulance,
  AnalyticsOverview,
  AuditEntry,
  CommandRow,
  DetectionRow,
  EmergencyRow,
  Hospital,
  JunctionDetail,
  JunctionSummary,
  LiveSession,
  OverrideResult,
  PortalAlert,
  PortalUser,
  Paged,
  TelemetryRow,
} from "@/types/portal";

// ---- users (ADMIN) ----------------------------------------------------------

export function listUsers(params: {
  limit?: number;
  offset?: number;
  role?: string;
} = {}): Promise<Paged<PortalUser>> {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]),
  );
  return request<Paged<PortalUser>>(`/admin/users?${q}`);
}

export function createUser(body: {
  email: string;
  password: string;
  role: string;
  hospital_id?: string;
  junction_ids?: string[];
}): Promise<PortalUser> {
  return request<PortalUser>("/admin/users", { method: "POST", body });
}

export function patchUser(
  uid: string,
  body: {
    is_active?: boolean;
    role?: string;
    hospital_id?: string | null;
    junction_ids?: string[];
  },
): Promise<PortalUser> {
  return request<PortalUser>(`/admin/users/${uid}`, { method: "PATCH", body });
}

export function resetUserPassword(
  uid: string,
  newPassword?: string,
): Promise<{ user_id: string; password: string }> {
  return request(`/admin/users/${uid}/password-reset`, {
    method: "POST",
    body: newPassword ? { new_password: newPassword } : {},
  });
}

// ---- hospitals --------------------------------------------------------------

export function listHospitals(): Promise<Hospital[]> {
  return request<Hospital[]>("/admin/hospitals");
}

export function createHospital(body: {
  name: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  phone?: string;
}): Promise<{ id: string }> {
  return request("/admin/hospitals", { method: "POST", body });
}

export function patchHospital(
  hid: string,
  body: Partial<{ name: string; address: string; latitude: number; longitude: number; phone: string }>,
): Promise<{ id: string }> {
  return request(`/admin/hospitals/${hid}`, { method: "PATCH", body });
}

// ---- ambulances (ADMIN all / HOSPITAL own) ----------------------------------

export function listAmbulances(): Promise<Ambulance[]> {
  return request<Ambulance[]>("/ambulances");
}

export function createAmbulance(body: {
  vehicle_no: string;
  driver_id?: string;
  hospital_id?: string;
}): Promise<{ id: string }> {
  return request("/ambulances", { method: "POST", body });
}

export function patchAmbulance(
  aid: string,
  body: Partial<{
    driver_id: string | null;
    hospital_id: string;
    on_duty: boolean;
    vehicle_no: string;
  }>,
): Promise<{ id: string }> {
  return request(`/ambulances/${aid}`, { method: "PATCH", body });
}

/** Drivers directory derived from the visible fleet (ADMIN all / HOSPITAL own). */
export function listFleetDrivers(): Promise<
  { driver_id: string; email: string | null; ambulance_id: string | null; vehicle_no: string | null }[]
> {
  return request("/admin/fleet/drivers");
}

// ---- live operations / alerts / analytics / audit ---------------------------

export function fetchLive(): Promise<{ items: LiveSession[] }> {
  return request("/admin/live");
}

export function fetchAlerts(limit = 50): Promise<PortalAlert[]> {
  return request(`/admin/alerts?limit=${limit}`);
}

export function fetchAnalytics(days = 7): Promise<AnalyticsOverview> {
  return request(`/admin/analytics/overview?days=${days}`);
}

export function fetchAudit(params: { limit?: number; offset?: number; action?: string } = {}): Promise<
  Paged<AuditEntry>
> {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]),
  );
  return request<Paged<AuditEntry>>(`/admin/audit?${q}`);
}

export function fetchEmergencies(params: {
  limit?: number;
  offset?: number;
  status?: string;
  junction_id?: string;
  ambulance_id?: string;
  from?: string;
  to?: string;
} = {}): Promise<Paged<EmergencyRow>> {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]),
  );
  return request<Paged<EmergencyRow>>(`/admin/emergencies?${q}`);
}

// ---- junctions / commands / overrides / devices -----------------------------

export function listJunctions(): Promise<JunctionSummary[]> {
  return request<JunctionSummary[]>("/junctions");
}

export function getJunction(jid: string): Promise<JunctionDetail> {
  return request<JunctionDetail>(`/junctions/${jid}`);
}

export function createJunction(body: {
  name: string;
  latitude: number;
  longitude: number;
  radius_m?: number;
}): Promise<{ id: string }> {
  return request<{ id: string }>("/junctions", { method: "POST", body });
}

export function patchJunction(
  jid: string,
  body: Partial<{ name: string; latitude: number; longitude: number; radius_m: number; is_active: boolean }>,
): Promise<{ id: string }> {
  return request(`/junctions/${jid}`, { method: "PATCH", body });
}

export function deleteJunction(jid: string): Promise<{ deleted: boolean }> {
  return request(`/junctions/${jid}`, { method: "DELETE" });
}

export function overrideJunction(
  jid: string,
  action: "FORCE_RELEASE" | "HOLD" | "REISSUE",
  reason: string,
): Promise<OverrideResult> {
  return request<OverrideResult>(`/junctions/${jid}/override`, {
    method: "POST",
    body: { action, reason },
  });
}

export function listCommands(params: {
  junction_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
  since?: string;
  until?: string;
} = {}): Promise<CommandRow[]> {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]),
  );
  return request<CommandRow[]>(`/commands/admin/list?${q}`);
}

export function listDevices(): Promise<
  { id: string; junction_id: string; online: boolean; last_seen: string | null }[]
> {
  return request("/admin/devices/status");
}

export function registerDevice(junctionId: string, name: string): Promise<{ device_id: string; api_key: string }> {
  return request(`/admin/devices/register?junction_id=${junctionId}&name=${encodeURIComponent(name)}`, {
    method: "POST",
  });
}

export function rotateDeviceKey(deviceId: string): Promise<{ device_id: string; api_key: string }> {
  return request(`/admin/devices/${deviceId}/rotate-key`, { method: "POST" });
}

export function fetchMqttHealth(): Promise<{ connected: boolean; outbox: number }> {
  return request("/admin/mqtt/health");
}

export function fetchNotificationPrefs(): Promise<Record<string, boolean>> {
  return request("/admin/notification-prefs");
}

export function saveNotificationPrefs(prefs: Record<string, boolean>): Promise<Record<string, boolean>> {
  return request("/admin/notification-prefs", { method: "PUT", body: { prefs } });
}

export function listTelemetry(junctionId: string, limit = 50): Promise<Paged<TelemetryRow>> {
  return request(`/telemetry?junction_id=${junctionId}&limit=${limit}`);
}

export function listDetections(params: { junction_id?: string; limit?: number; offset?: number } = {}): Promise<
  { items: DetectionRow[]; limit: number; offset: number; total: number } | DetectionRow[]
> {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]),
  );
  return request<DetectionRow[] | { items: DetectionRow[]; limit: number; offset: number; total: number }>(`/vision/detections?${q}`);
}

// ---- self service (HOSPITAL / POLICE) ---------------------------------------

/** Change the signed-in user's password (other sessions are signed out). */
export function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ changed: true }> {
  return request("/auth/change-password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
  });
}
