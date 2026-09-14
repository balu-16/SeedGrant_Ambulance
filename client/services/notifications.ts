/**
 * Expo push notification service (expo-notifications).
 *
 * Active push path (EAS development build ready; Expo Go still works):
 * dev builds REQUIRE the EAS projectId for token issuance, Expo Go does not.
 * Delivery runs over FCM transport on Android via the Expo Push Service —
 * Android FCM credentials come from `client/google-services.json` (wired via
 * `android.googleServicesFile` in app.json, consumed by EAS Build/prebuild).
 * No native FCM code or Gradle edits in JS — do NOT add firebase-bom.
 *
 * Responsibilities:
 *  - configure the notification handler + Android channel (call once at startup)
 *  - request OS notification permissions
 *  - fetch the Expo Push Token (physical device only)
 *  - persist the token locally + POST it to FastAPI `POST /api/v1/push/register`
 *  - foreground/background listeners + logout unregister (best-effort)
 */

import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";

import { isApiEnabled, request } from "./api";

/** Local cache of the last issued token (runtime use; EXPO_PUSH_TOKEN stays manual). */
export const PUSH_TOKEN_KEY = "ambulance-driver:push-token:v1";

/** Flag so the welcome notification fires only once ever (first grant). */
export const WELCOME_NOTIFIED_KEY = "ambulance-driver:welcome-notified:v1";

/** EAS projectId when running inside a dev build (undefined in Expo Go). */
function easProjectId(): string | undefined {
  const id = Constants.expoConfig?.extra?.eas?.projectId as string | undefined;
  return id && id.length > 0 && !id.startsWith("REPLACE_WITH") ? id : undefined;
}

/** How incoming notifications behave while the app is foregrounded. */
export function configureNotifications(): void {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldPlaySound: true,
      shouldSetBadge: true,
      // Banner + list presentation on iOS; no-op on Android.
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });

  // Android requires a channel before anything can be displayed.
  if (Platform.OS === "android") {
    void Notifications.setNotificationChannelAsync("default", {
      name: "Default",
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#1475FF",
    });
  }
}

/**
 * Ask the OS for notification permission.
 * @returns true when permission is granted (or already granted).
 */
export async function requestPermissions(): Promise<boolean> {
  // Push tokens are unavailable on web and on simulators/emulators.
  if (Platform.OS === "web" || !Device.isDevice) {
    return false;
  }
  const current = await Notifications.getPermissionsAsync();
  if (current.granted) {
    return true;
  }
  const requested = await Notifications.requestPermissionsAsync();
  return requested.granted;
}

/**
 * Fetch the Expo Push Token (`ExponentPushToken[...]`).
 * Call this after `requestPermissions()` resolves true.
 *
 * Dev builds require the EAS projectId (read from app config `extra.eas`);
 * Expo Go issues tokens without it. The token is cached to AsyncStorage.
 *
 * @returns the token string, or null when unavailable (web/simulator/denied).
 */
export async function getExpoPushToken(): Promise<string | null> {
  if (Platform.OS === "web" || !Device.isDevice) {
    return null;
  }
  try {
    const projectId = easProjectId();
    const { data } = projectId
      ? await Notifications.getExpoPushTokenAsync({ projectId })
      : await Notifications.getExpoPushTokenAsync();
    await AsyncStorage.setItem(PUSH_TOKEN_KEY, data);
    return data;
  } catch {
    return null;
  }
}

/**
 * Send the Expo Push Token to the FastAPI backend.
 * POSTs `{player_id: token, expo_push_token: token, device_type, app_version}`
 * to `/api/v1/push/register` through the shared `request()` client (auth
 * header + error handling inherited). Silent no-op when unconfigured (keeps
 * UI code free of hardcoded tokens/URLs).
 */
export async function sendTokenToBackend(
  token: string,
  accessToken?: string,
): Promise<boolean> {
  try {
    if (!isApiEnabled() || !accessToken) return false;
    await request("/push/register", {
      method: "POST",
      body: {
        player_id: token,
        expo_push_token: token,
        device_type: Platform.OS,
        app_version: Constants.expoConfig?.version ?? "1.0.0",
      },
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Fire the once-ever "Thank you for subscribing" local notification.
 * Call right after the OS permission is granted (and the token is issued).
 * No-op on web/simulators, when already shown, or on any failure — the
 * flag is only set after a successful schedule, so a failed attempt is
 * retried on the next login instead of being lost or repeated.
 *
 * @returns true when the welcome notification was scheduled now.
 */
export async function scheduleWelcomeNotification(): Promise<boolean> {
  try {
    if (Platform.OS === "web" || !Device.isDevice) return false;
    if (await AsyncStorage.getItem(WELCOME_NOTIFIED_KEY)) return false;
    await Notifications.scheduleNotificationAsync({
      content: {
        title: "Thank you for subscribing!",
        body: "You'll receive emergency alerts, signal-priority updates and junction releases here. You can manage alerts anytime in Profile → Settings.",
        sound: true,
      },
      trigger: null,
    });
    await AsyncStorage.setItem(WELCOME_NOTIFIED_KEY, "1");
    return true;
  } catch {
    return false;
  }
}

/** Last notification received while foreground (for UI badges; null when none). */
export type NotificationListenerCleanup = () => void;
/**
 * Subscribe to foreground notifications + user taps.
 * Must be called once (e.g. root layout); returns an unsubscribe function.
 * Handlers are best-effort — never throw.
 */
export function addNotificationListeners(callbacks?: {
  onReceived?: (notification: Notifications.Notification) => void;
  onResponse?: (response: Notifications.NotificationResponse) => void;
  onTokenRefresh?: (token: string) => void;
}): NotificationListenerCleanup {
  const subs: { remove: () => void }[] = [];
  try {
    subs.push(
      Notifications.addNotificationReceivedListener((notification) => {
        try {
          callbacks?.onReceived?.(notification);
        } catch {
          /* ignore handler errors */
        }
      }),
    );
    subs.push(
      Notifications.addNotificationResponseReceivedListener((response) => {
        try {
          callbacks?.onResponse?.(response);
        } catch {
          /* ignore handler errors */
        }
      }),
    );
    // FCM token refresh (dev builds): re-cache + notify caller to re-register.
    subs.push(
      Notifications.addPushTokenListener((pushToken) => {
        try {
          const refreshed = pushToken.data;
          if (typeof refreshed === "string" && refreshed.length > 0) {
            void AsyncStorage.setItem(PUSH_TOKEN_KEY, refreshed).catch(
              () => undefined,
            );
            callbacks?.onTokenRefresh?.(refreshed);
          }
        } catch {
          /* ignore */
        }
      }),
    );
  } catch {
    /* listeners unavailable (web/unit tests) — return no-op cleanup */
  }
  return () => {
    for (const s of subs) {
      try {
        s.remove();
      } catch {
        /* ignore */
      }
    }
  };
}

/** Cached token from the last successful `getExpoPushToken()` (null when none). */
export async function getCachedPushToken(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(PUSH_TOKEN_KEY);
  } catch {
    return null;
  }
}

/**
 * Remove this device's push subscription server-side + clear the local cache.
 * Best-effort: always clears local cache, never throws. Call on logout.
 */
export async function unregisterTokenFromBackend(
  token?: string | null,
): Promise<boolean> {
  const target = token ?? (await getCachedPushToken());
  try {
    await AsyncStorage.removeItem(PUSH_TOKEN_KEY);
  } catch {
    /* keep going — server cleanup below */
  }
  if (!target || !isApiEnabled()) return false;
  try {
    await request(`/push/${encodeURIComponent(target)}`, { method: "DELETE" });
    return true;
  } catch {
    return false;
  }
}
