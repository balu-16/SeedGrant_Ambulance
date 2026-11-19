/**
 * Backend base URL — single source for services/api.ts and
 * services/portalAuth.ts (no import cycle between the two).
 *
 * In dev, Vite proxies `/api` → http://localhost:8000 (see vite.config.ts).
 * In production (Vercel) the backend URL comes from `VITE_API_URL`
 * (e.g. https://seedgrant-backend.onrender.com/api/v1).
 */

function normalizeBase(raw: string | undefined): string {
  let b = (raw ?? "").trim().replace(/\/+$/, "");
  if (!b) return "/api/v1";
  // Accept bare origin (…onrender.com) or full prefix (…/api/v1); never double it.
  if (!/\/api\/v1$/i.test(b)) b += "/api/v1";
  return b;
}

export const API_BASE = normalizeBase(
  import.meta.env.VITE_API_URL as string | undefined,
);

if (import.meta.env.PROD && API_BASE === "/api/v1") {
  console.warn(
    "VITE_API_URL is unset — admin portal will call same-origin /api/v1 and fail. Set VITE_API_URL=https://seedgrant-backend.onrender.com/api/v1 in Vercel.",
  );
}

/** Fetch timeout shared by both clients. */
export const TIMEOUT_MS = 15000;
