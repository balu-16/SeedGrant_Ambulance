/**
 * Typed contracts for the admin-portal backend endpoints (Phase 1 contract —
 * see ADMIN_PORTAL_PLAN.md §5). All calls go through services/api.ts
 * request<T>() so they inherit single-flight refresh + envelope unwrapping.
 */

export type PortalRole = "ADMIN" | "HOSPITAL" | "POLICE";

export interface PortalUser {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  hospital_id: string | null;
  junction_ids: string[];
  created_at: string;
}

export interface Hospital {
  id: string;
  name: string;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  phone: string | null;
  created_at: string;
  updated_at: string;
}

export interface Ambulance {
  id: string;
  vehicle_no: string;
  driver_id: string | null;
  hospital_id: string | null;
  on_duty: boolean;
}

export interface LiveCommand {
  id: string;
  junction_id: string;
  type: string;
  status: string;
  approach: string;
}

export interface LiveSession {
  id: string;
  status: string;
  started_at: string;
  driver: { id: string; email: string };
  ambulance: { id: string; vehicle_no: string };
  latest_gps: { latitude: number; longitude: number; recorded_at: string } | null;
  commands: LiveCommand[];
}

export type AlertType = "device_offline" | "command_expired" | "session_timed_out";

export interface PortalAlert {
  type: AlertType;
  severity: "high" | "medium" | "low";
  message: string;
  at: string;
  refs: Record<string, string>;
}

export interface AnalyticsOverview {
  days: number;
  emergencies: {
    total: number;
    by_status: Record<string, number>;
    avg_duration_minutes: number | null;
  };
  commands: { total: number; by_status: Record<string, number> };
  junctions: { junction_id: string; emergencies: number }[];
  devices: { online: number; total: number };
}

export interface AuditEntry {
  id: string;
  actor: string;
  action: string;
  entity: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface CommandRow {
  id: string;
  type: string;
  status: string;
  approach: string;
  junction_id: string;
  session_id: string | null;
  correlation_id: string;
  expires_at: string | null;
  ack_at: string | null;
  retry_count: number;
  created_at: string;
}

export interface OverrideResult {
  junction_id: string;
  action: "FORCE_RELEASE" | "HOLD" | "REISSUE";
  command: {
    id: string;
    type: string;
    status: string;
    approach: string;
    correlation_id: string;
    retry_count: number;
  };
}

export interface JunctionSummary {
  id: string;
  name: string;
  latitude: number | null;
  longitude: number | null;
}

export interface JunctionApproach {
  direction: string;
  heading_min: number | null;
  heading_max: number | null;
}

export interface JunctionDetail {
  id: string;
  name: string;
  approaches: JunctionApproach[];
}

export interface DeviceStatus {
  id: string;
  junction_id: string;
  online: boolean;
  last_seen: string | null;
}

export interface TelemetryRow {
  id: string;
  junction_id: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface DetectionRow {
  id: string;
  session_id: string | null;
  junction_id: string | null;
  vehicle_class: string;
  class_name: string;
  confidence: number;
  bbox: Record<string, unknown>;
  detected_at: string;
}

export interface EmergencyRow {
  id: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  ended_reason: string | null;
  driver_email: string | null;
  ambulance_vehicle_no: string | null;
}

export interface Paged<T> {
  items: T[];
  limit: number;
  offset: number;
}
