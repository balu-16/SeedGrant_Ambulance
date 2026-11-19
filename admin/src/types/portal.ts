/**
 * Typed contracts for the admin-portal backend endpoints (interface contract
 * §3/§5/§6 — see /tmp/seedgrant_baseline/contract.md). All calls go through
 * services/api.ts request<T>() so they inherit single-flight refresh +
 * envelope unwrapping.
 */

export interface PortalUser {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  hospital_id: string | null;
  junction_ids: string[];
  created_at: string;
  last_login: string | null;
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
  /** Owning hospital snapshot (contract §3) — null on legacy rows. */
  owner_hospital_id?: string | null;
  commands: LiveCommand[];
}

/** Per-junction live state from GET /admin/live (contract §5). */
export interface JunctionState {
  name: string;
  online: boolean;
  last_seen_at: string | null;
  /** null when the latest telemetry payload has no "state" key → UI shows "Unknown". */
  state: string | null;
  telemetry: Record<string, unknown> | null;
  telemetry_at: string | null;
}

/** GET /admin/live data (contract §5): items + uncapped total + snapshot time. */
export interface LiveData {
  items: LiveSession[];
  junction_states: Record<string, JunctionState>;
  /** Uncapped count of authorized active-family sessions (before the cap). */
  total: number;
  cap: number;
  /** Server time the snapshot was taken. */
  observed_at: string;
}

export type AlertType =
  | "device_offline"
  | "command_expired"
  | "session_timed_out"
  | "emergency_started"
  | "emergency_ended";

export interface PortalAlert {
  type: AlertType;
  /** Values the backend emits (admin.py alerts feed + derived events). */
  severity: "info" | "warning" | "critical";
  message: string;
  at: string;
  refs: Record<string, string>;
}

/** request→acknowledgement metric (contract §5) — device receipt, not a
 * physical crossing time. Replaces the removed `crossing` key. */
export interface RequestToAck {
  metric: "request_to_ack";
  p50_minutes: number | null;
  p95_minutes: number | null;
  samples: number;
  unit: string;
  timezone: string;
  note: string;
}

export interface AnalyticsOverview {
  days: number;
  emergencies: {
    total: number;
    by_status: Record<string, number>;
    avg_duration_minutes: number | null;
  };
  /** `current_pending` = live PENDING/SENT count (contract §5). */
  commands: { total: number; by_status: Record<string, number>; current_pending?: number };
  request_to_ack?: RequestToAck;
  hourly_histogram?: number[];
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
  /** Contract §6 envelope: 1-based attempt + per-junction sequence. */
  attempt?: number;
  junction_seq?: number | null;
  issued_at?: string | null;
  created_at: string;
}

/** Command identity block shared by the override response (contract §6). */
export interface CommandIdentity {
  id: string;
  type: string;
  status: string;
  approach: string;
  correlation_id: string;
  attempt: number;
  expires_at: string | null;
}

export interface OverrideResult {
  /** The junction the override targeted (echoed for the log). */
  junction_id?: string;
  action: "FORCE_RELEASE" | "HOLD" | "REISSUE";
  /** The action's primary command (null when nothing applied). */
  command: CommandIdentity | null;
  /** Release command published by HOLD when a delivered request had to be undone. */
  release: CommandIdentity | null;
  /** Publish state of the primary command ("PENDING" until the device acks). */
  delivery: { status: "PENDING" | "ACKNOWLEDGED" | "PUBLISH_FAILED"; via: string } | null;
  message: string;
}

export interface JunctionSummary {
  id: string;
  name: string;
  latitude: number | null;
  longitude: number | null;
  is_active?: boolean;
  radius_m?: number | null;
}

export interface JunctionApproach {
  direction: string;
  heading_min: number | null;
  heading_max: number | null;
  entry_lat?: number | null;
  entry_lon?: number | null;
}

export interface JunctionDetail {
  id: string;
  name: string;
  is_active?: boolean;
  radius_m?: number | null;
  approaches: JunctionApproach[];
}

export interface DeviceStatus {
  id: string;
  junction_id: string;
  online: boolean;
  last_seen: string | null;
}

export interface TelemetryRow {
  payload: Record<string, unknown>;
  at: string;
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
  /** Owning-hospital snapshot (contract §3) — null until reviewed/set. */
  owner_hospital_id: string | null;
  owner_hospital_name: string | null;
}

export interface Paged<T> {
  items: T[];
  limit: number;
  offset: number;
  total?: number;
}

// ---- GET /portal/status (contract §1) ----

export interface PortalStatus {
  simulation: boolean;
  server_time: string;
  manual_controls: boolean;
  freshness: {
    gps_stale_seconds: number;
    portal_stale_seconds: number;
    device_offline_seconds: number;
  };
}

// ---- GET /emergencies/{sid}/timeline (contract §4, shape unchanged) ----

export interface TimelineEvent {
  id: string;
  kind: "command" | "audit";
  type: string;
  status: string | null;
  junction_id?: string;
  approach?: string;
  at: string | null;
}

export interface TimelineResponse {
  session_id: string;
  items: TimelineEvent[];
}
