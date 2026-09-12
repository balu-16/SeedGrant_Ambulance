/**
 * Auth-token storage for the portal (web only → localStorage).
 *
 * Same getTokens/saveTokens/clearTokens contract as the driver app's
 * client/services/tokenStorage.ts; only the key differs so the two never
 * collide. Web has no Keychain/Keystore equivalent — the planned hardening
 * pass (HttpOnly cookie sessions) lands server-side.
 */

import type { Tokens } from "@/types/api";

export const TOKENS_KEY = "admin-portal:tokens:v1";

function parseTokens(raw: string): Tokens | null {
  try {
    const v = JSON.parse(raw) as Partial<Tokens>;
    return typeof v.access_token === "string" &&
      typeof v.refresh_token === "string"
      ? { access_token: v.access_token, refresh_token: v.refresh_token }
      : null;
  } catch {
    return null;
  }
}

export function getTokens(): Tokens | null {
  try {
    const raw = localStorage.getItem(TOKENS_KEY);
    return raw ? parseTokens(raw) : null;
  } catch {
    return null;
  }
}

export function saveTokens(tokens: Tokens): void {
  localStorage.setItem(TOKENS_KEY, JSON.stringify(tokens));
}

export function clearTokens(): void {
  try {
    localStorage.removeItem(TOKENS_KEY);
  } catch {
    // Ignore storage failures (private mode etc.) — logout must not throw.
  }
}
