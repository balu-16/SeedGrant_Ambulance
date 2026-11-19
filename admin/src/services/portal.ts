/**
 * Portal endpoint functions (typed contracts in types/portal.ts, interface
 * contract in /tmp/seedgrant_baseline/contract.md). Every function routes
 * through services/api.ts request<T>() — no fetch calls anywhere else except
 * exportEmergenciesCsv, which streams a blob with the Authorization header.
 */

import { API_BASE } from "@/services/apiBase";
import { ApiError } from "@/services/ApiError";
import { getAccessToken } from "@/services/portalAuth";
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
  LiveData,
  OverrideResult,
  Paged,
  PortalAlert,
  PortalStatus,
  PortalUser,
  TelemetryRow,
  TimelineResponse,
} from "@/types/portal";

// ---- users (ADMIN) ----------------------------------------------------------

export function listUsers(
  params: {
    q?: string;
    role?: string;
    status?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<Paged<PortalUser>> {
  const q = new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => [k, String(v)]),
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

// ---- portal status (contract §1) ---------------------------------------------

/** GET /portal/status — polled once per session (staleTime 60s). */
export function fetchPortalStatus(): Promise<PortalStatus> {
  return request<PortalStatus>("/portal/status");
}

// ---- live operations / alerts / analytics / audit ---------------------------

export function fetchLive(): Promise<LiveData> {
  return request<LiveData>("/admin/live");
}

export function fetchAlerts(limit = 50): Promise<PortalAlert[]> {
  return request<PortalAlert[]>(`/admin/alerts?limit=${limit}`);
}

export function fetchAnalytics(days = 7): Promise<AnalyticsOverview> {
  return request<AnalyticsOverview>(`/admin/analytics/overview?days=${days}`);
}

export function fetchAudit(params: { limit?: number; offset?: number; action?: string } = {}): Promise<
  Paged<AuditEntry>
> {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]),
  );
  return request<Paged<AuditEntry>>(`/admin/audit?${q}`);
}

// ---- emergencies (contract §3): filters, export, timeline --------------------

/** Server-side emergency filters (contract §3) shared by list + export. */
export interface EmergencyFilters {
  status?: string;
  /** ISO datetime (or date) on started_at — inclusive. */
  from?: string;
  to?: string;
  ambulance_id?: string;
  /** Session has ≥1 command at that junction. */
  junction_id?: string;
  /** ADMIN only — hospital scope always wins for HOSPITAL callers. */
  hospital_id?: string;
}

/** Build the query string for the emergencies list/export endpoints. */
export function emergencyFilterParams(
  filters: EmergencyFilters = {},
): URLSearchParams {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") q.set(key, value);
  }
  return q;
}

export function fetchEmergencies(
  params: EmergencyFilters & { limit?: number; offset?: number } = {},
): Promise<Paged<EmergencyRow>> {
  const q = emergencyFilterParams(params);
  return request<Paged<EmergencyRow>>(`/admin/emergencies?${q}`);
}

/**
 * Server-side CSV export (contract §3): fetch with the Authorization header →
 * blob → download. Never a bare <a href> to the API — the export must carry
 * credentials and surface failures as catchable errors.
 */
export async function exportEmergenciesCsv(
  filters: EmergencyFilters = {},
): Promise<void> {
  const token = getAccessToken();
  let res: Response;
  try {
    res = await fetch(
      `${API_BASE}/admin/emergencies/export.csv?${emergencyFilterParams(filters)}`,
      {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: "same-origin",
      },
    );
  } catch (e) {
    throw new ApiError(
      e instanceof Error ? `Network error: ${e.message}` : "Network error",
      0,
      "NETWORK_ERROR",
    );
  }
  if (!res.ok) {
    let message = `Export failed (${res.status})`;
    try {
      const payload = (await res.json()) as { error?: { message?: string } };
      if (payload.error?.message) message = payload.error.message;
    } catch {
      // Not an envelope — keep the generic message.
    }
    throw new ApiError(message, res.status, res.status === 401 ? "UNAUTHORIZED" : "EXPORT_FAILED");
  }
  const blob = await res.blob();
  // Prefer the server's Content-Disposition filename.
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match?.[1] ?? "emergencies-export.csv";
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** GET /emergencies/{sid}/timeline (contract §4 — admin + owning hospital). */
export function fetchEmergencyTimeline(sid: string): Promise<TimelineResponse> {
  return request<TimelineResponse>(`/emergencies/${sid}/timeline`);
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
