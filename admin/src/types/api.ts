/**
 * API models shared by the portal — mirrors the FastAPI envelope and auth
 * schemas served at /api/v1 (same backend the driver app uses).
 */

export type Role = "admin" | "hospital" | "police" | "driver";

/** Normalize any role string from the backend to lowercase canonical form. */
export function normalizeRole(r: string): Role {
  const v = r.trim().toLowerCase();
  if (v === "admin" || v === "hospital" || v === "police" || v === "driver")
    return v;
  throw new Error(`Unknown role from backend: ${r}`);
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
