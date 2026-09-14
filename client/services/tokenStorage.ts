/**
 * Auth-token storage: Keychain/Keystore via expo-secure-store on native,
 * AsyncStorage on web (SecureStore does not exist on web, and the Playwright
 * e2e suite runs on web — web behavior must stay identical).
 *
 * Same key and same getTokens/saveTokens/clearTokens contract as before; only
 * the backing store changes on native so JWTs are no longer plaintext in
 * AsyncStorage.
 *
 * Implementation note: this module intentionally avoids importing
 * `react-native` (Platform) and `expo-secure-store` statically. The react-native
 * entry is Flow syntax that cannot load under the node unit-test runner, and
 * services/api.ts (which re-exports this storage) is part of that import
 * graph. Web/native detection uses `document` (present in browsers only —
 * React Native and node never define it), and the native module is imported
 * lazily on first use.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import type { BackendTokens } from "./api";

export const TOKENS_KEY = "ambulance-driver:tokens:v1";

const isWeb = typeof document !== "undefined";

type SecureStoreModule = typeof import("expo-secure-store");
let secureStorePromise: Promise<SecureStoreModule | null> | null = null;

/** Lazily resolve expo-secure-store on native (null when unavailable/web). */
function getSecureStore(): Promise<SecureStoreModule | null> {
  if (isWeb) return Promise.resolve(null);
  if (!secureStorePromise) {
    secureStorePromise = import("expo-secure-store")
      .then((mod) => {
        const store = (mod as { default?: SecureStoreModule }).default ?? mod;
        return store;
      })
      .catch(() => null);
  }
  return secureStorePromise;
}

function parseTokens(raw: string): BackendTokens | null {
  try {
    const v = JSON.parse(raw) as Partial<BackendTokens>;
    return typeof v.access_token === "string" &&
      typeof v.refresh_token === "string"
      ? { access_token: v.access_token, refresh_token: v.refresh_token }
      : null;
  } catch {
    return null;
  }
}

export async function getTokens(): Promise<BackendTokens | null> {
  try {
    const store = await getSecureStore();
    if (!store) {
      // Web (or native fallback if the module is unavailable).
      const raw = await AsyncStorage.getItem(TOKENS_KEY);
      return raw ? parseTokens(raw) : null;
    }
    const raw = await store.getItemAsync(TOKENS_KEY);
    if (raw) return parseTokens(raw);
    // One-time migration: tokens written as plaintext by older app versions
    // move into the Keychain/Keystore and their plaintext copy is removed.
    const legacy = await AsyncStorage.getItem(TOKENS_KEY);
    if (legacy) {
      const tokens = parseTokens(legacy);
      await AsyncStorage.removeItem(TOKENS_KEY).catch(() => undefined);
      if (tokens) {
        await store.setItemAsync(TOKENS_KEY, legacy);
        return tokens;
      }
    }
    return null;
  } catch {
    return null;
  }
}

export async function saveTokens(tokens: BackendTokens): Promise<void> {
  const raw = JSON.stringify(tokens);
  const store = await getSecureStore();
  if (!store) {
    await AsyncStorage.setItem(TOKENS_KEY, raw);
    return;
  }
  await store.setItemAsync(TOKENS_KEY, raw);
  // Best effort: drop any plaintext copy left by older app versions.
  await AsyncStorage.removeItem(TOKENS_KEY).catch(() => undefined);
}

export async function clearTokens(): Promise<void> {
  const store = await getSecureStore();
  const tasks: Promise<void>[] = [AsyncStorage.removeItem(TOKENS_KEY)];
  if (store) tasks.push(store.deleteItemAsync(TOKENS_KEY));
  await Promise.all(tasks.map((task) => task.catch(() => undefined)));
}
