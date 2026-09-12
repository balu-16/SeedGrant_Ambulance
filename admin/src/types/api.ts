/**
 * API models shared by the portal — mirrors the FastAPI envelope and auth
 * schemas served at /api/v1 (same backend the driver app uses).
 */

export type Role = "ADMIN" | "HOSPITAL" | "POLICE" | "DRIVER";

/** Roles allowed on this portal (DRIVER uses the mobile app, not the web). */
export const PORTAL_ROLES: readonly Role[] = ["ADMIN", "HOSPITAL", "POLICE"];

export function isPortalRole(role: string): role is "ADMIN" | "HOSPITAL" | "POLICE" {
  return (PORTAL_ROLES as readonly string[]).includes(role);
}

export interface AuthUser {
  id: string;
  email: string;
  role: Role;
  name?: string | null;
  hospital_id?: string | null;
  /** POLICE only: junctions this officer is assigned to (from /auth/me). */
  junction_ids?: string[];
}

export interface Tokens {
  access_token: string;
  refresh_token: string;
}

/** POST /auth/login response. */
export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: AuthUser;
}

/** Standard backend envelope: { success, data, error: { code, message } }. */
export interface ApiEnvelope<T> {
  success?: boolean;
  data?: T;
  error?: { code?: string; message?: string };
}
