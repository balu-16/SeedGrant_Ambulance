import { Stack, router } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { ActivityIndicator, Pressable, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { AppProvider } from "@/store/AppProvider";
import { useApp } from "@/hooks/useApp";
import { Button, Txt } from "@/components/ui";
import { colors as c } from "@/constants/theme";
import { getTokens, isApiEnabled } from "@/services/api";
import {
  addNotificationListeners,
  configureNotifications,
  getExpoPushToken,
  requestPermissions,
  scheduleWelcomeNotification,
  sendTokenToBackend,
} from "@/services/notifications";
/**
 * Push setup: handler + permissions + token → backend register. Re-runs when
 * the auth state changes — registration needs the driver's access token,
 * which only exists after login (a mount-only setup would check before any
 * login and never register). Tapping a push routes to Home; background/quit
 * delivery is handled by the OS via FCM. Server events that push: emergency
 * start/end/cancel, priority requested, junction crossed, green confirmed
 * (Pi ACK), officer override, and session timed out — plus a once-ever
 * local "Thank you for subscribing" on the first grant.
 */
function usePushSetup() {
  const { state } = useApp();
  const authed = !!state.auth;
  useEffect(() => {
    configureNotifications();
    const unsubscribe = addNotificationListeners({
      onResponse: () => {
        // Tapping any push lands the driver on Home (active-emergency
        // context). Best-effort: auth guards still apply when logged out.
        try {
          router.push("/(tabs)/home");
        } catch {
          /* ignore navigation errors */
        }
      },
      onTokenRefresh: (refreshed) => {
        // FCM rotation: re-register without prompting again (needs auth).
        void (async () => {
          try {
            const tokens = await getTokens();
            if (tokens)
              await sendTokenToBackend(refreshed, tokens.access_token);
          } catch {
            /* best-effort */
          }
        })();
      },
    });
    if (!authed) return unsubscribe;
    let cancelled = false;
    (async () => {
      try {
        const granted = await requestPermissions();
        const token = granted ? await getExpoPushToken() : null;
        if (token && !cancelled) {
          const tokens = await getTokens();
          if (tokens) await sendTokenToBackend(token, tokens.access_token);
          // Immediate local acknowledgement of the fresh grant (once ever).
          await scheduleWelcomeNotification();
        }
      } catch {
        /* notifications are best-effort; app works without them */
      }
    })();
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [authed]);
}
/**
 * Root crash boundary: expo-router renders this if any route throws during
 * render, instead of the default framework error screen.
 */
export function ErrorBoundary({
  error,
  retry,
}: {
  error: Error;
  retry: () => void;
}) {
  return (
    <SafeAreaView
      style={{
        flex: 1,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: c.pale,
        padding: 25,
        gap: 16,
      }}
    >
      <Txt accessibilityRole="alert">Something went wrong.</Txt>
      <Txt muted>{error.message}</Txt>
      <Button title="Try again" onPress={retry} />
    </SafeAreaView>
  );
}
function Navigation() {
  const { state, hydrated, storageError, retryStorage, resetLocalData } =
    useApp();
  usePushSetup();
  // No backend URL configured → this build cannot do anything real. Show a
  // plain "not found"-style screen instead of any offline/demo behavior.
  if (!isApiEnabled()) {
    return (
      <SafeAreaView
        style={{
          flex: 1,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: c.pale,
          padding: 25,
          gap: 12,
        }}
      >
        <Txt style={{ fontSize: 28, fontWeight: "700" }}>404</Txt>
        <Txt accessibilityRole="alert">App not configured</Txt>
        <Txt muted style={{ textAlign: "center" }}>
          This build is missing its backend URL (EXPO_PUBLIC_API_URL) and
          cannot reach the SeedGrant control center. Install a configured
          build to continue.
        </Txt>
      </SafeAreaView>
    );
  }
  if (!hydrated)
    return (
      <SafeAreaView
        style={{
          flex: 1,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: c.pale,
          padding: 25,
          gap: 20,
        }}
      >
        {storageError ? (
          <>
            <Txt>{storageError}</Txt>
            <Button title="Retry" onPress={retryStorage} />
            <Txt muted>
              Resetting clears saved sessions and profile edits.
            </Txt>
            <Button
              title="Reset Local Data"
              tone="quiet"
              onPress={resetLocalData}
            />
          </>
        ) : (
          <ActivityIndicator size="large" color={c.blue} />
        )}
      </SafeAreaView>
    );
  return (
    <View style={{ flex: 1 }}>
      <Stack
        screenOptions={{
          headerShown: false,
          animation: state.settings.reducedMotion ? "none" : "fade",
          contentStyle: { backgroundColor: c.pale },
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Protected guard={!state.auth && !state.onboardingComplete}>
          <Stack.Screen name="onboarding" />
        </Stack.Protected>
        <Stack.Protected guard={!state.auth && state.onboardingComplete}>
          <Stack.Screen name="login" />
        </Stack.Protected>
        <Stack.Protected guard={!!state.auth}>
          <Stack.Screen name="(tabs)" />
        </Stack.Protected>
      </Stack>
      {storageError && (
        <Pressable
          onPress={retryStorage}
          style={{ backgroundColor: c.redLight, padding: 12 }}
        >
          <Txt accessibilityRole="alert" style={{ color: c.red }}>
            {storageError}
          </Txt>
        </Pressable>
      )}
    </View>
  );
}
export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AppProvider>
        <StatusBar style="dark" />
        <Navigation />
      </AppProvider>
    </SafeAreaProvider>
  );
}
