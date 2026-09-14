import { useEffect, useRef, useState } from "react";
import {
  Image,
  Platform,
  Pressable,
  StyleSheet,
  View,
  useWindowDimensions,
} from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import * as Linking from "expo-linking";
import * as Location from "expo-location";
import * as SMS from "expo-sms";
import { AmbulanceMark, Heartbeat } from "@/components/Artwork";
import { LiveRouteMap } from "@/components/LiveRouteMap";
import { EventTimeline } from "@/components/EventTimeline";
import {
  Avatar,
  Badge,
  Button,
  Card,
  Field,
  Header,
  Icon,
  IconButton,
  Page,
  Row,
  SectionTitle,
  Sheet,
  Txt,
  type IconName,
} from "@/components/ui";
import { colors as c, images } from "@/constants/theme";
import { useApp } from "@/hooks/useApp";
import { isBackendLinked } from "@/services/api";
import { listContacts } from "@/services/contacts";
import {
  backendCurrent,
  backendGps,
  backendHeartbeat,
  backendHospitals,
  backendJunctions,
  backendPatient,
  backendStart,
  backendStop,
  apiMyAmbulance,
  retrackBackendSession,
  stopActiveBackendSession,
  type NearbyJunction,
} from "@/services/emergency";
import {
  startBackgroundTracking,
  stopBackgroundTracking,
  flushOutbox,
  outboxLength,
} from "@/services/background-location";
import {
  requestGpsPermission,
  watchGps,
  type GpsFix,
} from "@/services/location";
import {
  fetchRoute,
  formatDistance,
  formatEta,
  type LatLon,
} from "@/services/routing";
import { EMPTY_LOCATION } from "@/services/defaultState";
import { duration } from "@/utils/format";
import type { EmergencyContact, EventKind } from "@/types/models";

/** Backend terminal statuses — the server session is gone when one arrives. */
const TERMINAL_BACKEND_STATUSES = new Set([
  "COMPLETED",
  "CANCELLED",
  "TIMED_OUT",
]);
/** Mirrors server MAX_GPS_ACCURACY_M: worse fixes get 422 BAD_GPS. */
const MAX_USABLE_ACCURACY_M = 50;

function StatusCard({
  icon,
  label,
  value,
  detail,
  green,
  onPress,
  narrow,
}: {
  icon: IconName;
  label: string;
  value: string;
  detail: string;
  green?: boolean;
  onPress: () => void;
  narrow: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${label}: ${value}`}
      style={{ width: narrow ? "100%" : "48.5%" }}
    >
      <Card style={s.status}>
        <View
          style={{
            backgroundColor: green ? c.greenLight : c.blueLight,
            padding: 8,
            borderRadius: 25,
            alignSelf: "flex-start",
          }}
        >
          <Icon name={icon} size={26} color={green ? c.green : c.blue} />
        </View>
        <View style={{ flex: 1 }}>
          <Txt
            style={{
              fontSize: 11,
              lineHeight: 16,
              fontWeight: "600",
              marginBottom: 4,
            }}
          >
            {label}
          </Txt>
          <Txt
            style={{
              fontSize: 12,
              lineHeight: 17,
              fontWeight: "700",
              color: green ? c.green : c.navy,
            }}
          >
            {value}
          </Txt>
          <Txt muted style={{ fontSize: 10, lineHeight: 15, marginTop: 3 }}>
            {detail}
          </Txt>
        </View>
        <Icon name="chevron-right" size={20} color={c.muted} />
      </Card>
    </Pressable>
  );
}
export default function HomeScreen() {
  const { state, dispatch } = useApp();
  const router = useRouter();
  const { width, fontScale } = useWindowDimensions();
  const active = state.active;
  const location = active?.location ?? EMPTY_LOCATION;
  const [dialog, setDialog] = useState<
    | "route"
    | "events"
    | "connection"
    | "start"
    | "stop"
    | "ended"
    | "patient"
    | "hospital"
    | "notify"
    | null
  >(null);
  const [now, setNow] = useState(() => Date.now());
  const activeId = active?.id;
  // Backend-linked session (real API) — null when unlinked.
  const [backendSessionId, setBackendSessionId] = useState<string | null>(null);
  const [linked, setLinked] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void isBackendLinked().then((v) => {
      if (!cancelled) setLinked(v);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  // Reconcile with an in-progress backend session on mount (e.g. app restart).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!(await isBackendLinked())) return;
      try {
        const cur = await backendCurrent();
        if (!cancelled && cur.active) setBackendSessionId(cur.session_id);
      } catch {
        /* offline — nothing to reconcile yet */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    if (!activeId) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [activeId]);
  // Stream each new fix to the backend session (geofence/priority runs server-side).
  // Permission is requested for ANY active session (even offline) so the map
  // and distance are live; backend posting additionally needs a session id.
  const [liveFix, setLiveFix] = useState<{ fix: GpsFix; at: number } | null>(
    null,
  );
  const liveFixAt = liveFix?.at ?? 0;
  const [gpsLive, setGpsLive] = useState(false);
  const [gpsMode, setGpsMode] = useState<"live" | "stale">("stale");
  const [bgMode, setBgMode] = useState<string | null>(null);
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null);
  const [queuedCount, setQueuedCount] = useState(0);
  const gpsWatching = !!active;
  useEffect(() => {
    if (!gpsWatching) return;
    let watch: { stop: () => void } | null = null;
    let cancelled = false;
    let staleTimer: ReturnType<typeof setTimeout> | null = null;
    void requestGpsPermission().then(() => {
      if (cancelled) return;
      return watchGps((fix) => {
        if (cancelled) return;
        setLiveFix({ fix, at: Date.now() });
        setGpsLive(true);
        setGpsMode("live");
        dispatch({
          type: "liveFix",
          now: Date.now(),
          latitude: fix.latitude,
          longitude: fix.longitude,
          accuracy: fix.accuracy,
          speed: fix.speed,
        });
        if (staleTimer) clearTimeout(staleTimer);
        staleTimer = setTimeout(() => {
          if (!cancelled) {
            setGpsLive(false);
            setGpsMode("stale");
          }
        }, 10000);
      }).then((w) => {
        watch = cancelled ? (w.stop(), null) : w;
      });
    });
    return () => {
      cancelled = true;
      if (staleTimer) clearTimeout(staleTimer);
      setGpsLive(false);
      watch?.stop();
    };
  }, [gpsWatching, dispatch]);
  // Background tracking while a backend session runs (keeps working when the
  // app is backgrounded; foreground watch above covers the live UI).
  useEffect(() => {
    if (!backendSessionId || !activeId) return;
    let cancelled = false;
    void startBackgroundTracking(backendSessionId).then((m) => {
      if (!cancelled) {
        setBgMode(m);
        void outboxLength().then((n) => {
          if (!cancelled) setQueuedCount(n);
        });
      }
    });
    const hb = setInterval(() => {
      if (backendSessionId)
        void backendHeartbeat(backendSessionId).catch(() => undefined);
      void flushOutbox()
        .then((r) => {
          if (!cancelled) setQueuedCount(r.pending);
        })
        .catch(() => undefined);
    }, 60000);
    return () => {
      cancelled = true;
      clearInterval(hb);
      void stopBackgroundTracking();
    };
  }, [backendSessionId, activeId]);
  const liveFresh = gpsLive && liveFix !== null ? liveFix.fix : null;
  // A fix is only usable when fresh AND accurate enough for the backend —
  // worse fixes are rejected server-side with 422 BAD_GPS.
  const gpsUsable =
    liveFresh !== null &&
    (liveFresh.accuracy ?? Infinity) <= MAX_USABLE_ACCURACY_M;
  // Backend truth for the priority card (null = no command seen yet this session).
  const [backendPriority, setBackendPriority] = useState<
    "requested" | "released" | null
  >(null);
  const [backendError, setBackendError] = useState(false);
  const [serverEnded, setServerEnded] = useState<string | null>(null);
  // Real nearest junction from the backend GPS response; GET /junctions
  // resolves the server-side name for the id.
  const [nearbyJunction, setNearbyJunction] = useState<NearbyJunction | null>(
    null,
  );
  const [junctionNames, setJunctionNames] = useState<
    Record<string, string>
  >({});
  const nearest = nearbyJunction
    ? {
        name: junctionNames[nearbyJunction.junction_id] ?? "Junction",
        approach: nearbyJunction.approach,
        distanceM: nearbyJunction.distance_m,
      }
    : null;
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!(await isBackendLinked())) return;
      try {
        const list = await backendJunctions();
        if (!cancelled) {
          const map: Record<string, string> = {};
          for (const j of list) map[j.id] = j.name;
          setJunctionNames(map);
        }
      } catch {
        /* names stay id-based until the catalog loads */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [linked]);
  useEffect(() => {
    if (!backendSessionId || !active) return;
    // Backend-linked mode posts ONLY real fixes: the server runs its real
    // geofence/priority engine on what we send, so a fabricated fix could
    // trigger signal-priority commands at the wrong junction. Skip posting
    // while GPS is unusable and surface the weak-GPS state in the footer.
    if (!gpsUsable || liveFresh === null) return;
    let cancelled = false;
    const t0 = Date.now();
    void backendGps(backendSessionId, {
      latitude: liveFresh.latitude,
      longitude: liveFresh.longitude,
      accuracy: liveFresh.accuracy,
      speed: liveFresh.speed,
      heading: liveFresh.heading,
    })
      .then((res) => {
        if (cancelled) return;
        setBackendError(false);
        setLastLatencyMs(Date.now() - t0);
        setNearbyJunction(res.nearby?.[0] ?? null);
        const t = res.command?.type ?? "";
        const kind: EventKind | null =
          t === "PRIORITY_REQUEST" || t === "REISSUE"
            ? "requested"
            : t === "ACK_CONFIRMED"
              ? "granted"
              : t === "RELEASE_PRIORITY" ||
                  t === "FORCE_RELEASE" ||
                  t === "OVERRIDE_HOLD"
                ? "released"
                : null;
        if (!res.duplicate && kind && res.command) {
          // The events sheet shows the backend's real command stream.
          dispatch({
            type: "sessionEvent",
            event: {
              id: res.command.id,
              kind,
              timestamp: Date.now(),
              approach: res.command.approach,
            },
          });
        }
        if (
          t === "PRIORITY_REQUEST" ||
          t === "ACK_CONFIRMED" ||
          t === "REISSUE"
        ) {
          setBackendPriority("requested");
        } else if (
          t === "RELEASE_PRIORITY" ||
          t === "OVERRIDE_HOLD" ||
          t === "FORCE_RELEASE"
        ) {
          setBackendPriority("released");
        }
        if (TERMINAL_BACKEND_STATUSES.has(res.status)) {
          // The server session died (inactivity timeout / admin action).
          // End the local session and tell the driver instead of posting
          // into 409s forever while the UI claims "Emergency Active".
          setBackendSessionId(null);
          setBackendPriority(null);
          dispatch({ type: "stop", now: Date.now() });
          setServerEnded(res.status);
          setDialog("ended");
        }
      })
      .catch(() => {
        if (!cancelled) setBackendError(true);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendSessionId, liveFixAt, gpsUsable]);
  // When a backend session is feeding, the priority card shows backend truth —
  // the command stream from the GPS response, never a local guess.
  const backendDriving = !!backendSessionId && !!active;
  const priority = backendDriving
    ? backendPriority === "requested"
      ? "Signal Priority Sent"
      : backendPriority === "released"
        ? "Priority Released"
        : "No priority requested"
    : active?.priority === "granted"
      ? "Green Signal Granted"
      : active?.priority === "requested"
        ? "Signal Priority Sent"
        : active?.priority === "released"
          ? "Priority Released"
          : "Ready for Emergency";
  const startingRef = useRef(false);
  // Hospital picker (GET /hospitals, free-text fallback) + destination coords.
  const [hospitalOptions, setHospitalOptions] = useState<
    {
      id: string;
      name: string;
      latitude?: number | null;
      longitude?: number | null;
    }[]
  >([]);
  const [patientNotes, setPatientNotes] = useState("");
  const [patientSeverity, setPatientSeverity] = useState("stable");
  // SOS notify prompt: offered once per session right after a successful
  // start. Native only — SMS is unavailable on web, and the contacts list
  // lives on the backend so offline/demo sessions never prompt.
  const [notifyContacts, setNotifyContacts] = useState<EmergencyContact[]>([]);
  const notifiedThisSessionRef = useRef(false);
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!(await isBackendLinked())) return;
      try {
        const list = await backendHospitals();
        if (!cancelled) setHospitalOptions(list);
      } catch {
        /* offline — free text stays */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [linked]);
  const destination: LatLon | null = (() => {
    const match = hospitalOptions.find(
      (h) => h.name === (active?.hospital ?? state.ambulance.hospital),
    );
    if (
      match &&
      typeof match.latitude === "number" &&
      typeof match.longitude === "number"
    )
      return { latitude: match.latitude, longitude: match.longitude };
    // No hospital coordinates yet — no route/ETA until one is picked or the
    // backend list loads. Never fall back to fabricated coordinates.
    return null;
  })();
  const origin: LatLon | null = liveFresh
    ? { latitude: liveFresh.latitude, longitude: liveFresh.longitude }
    : active
      ? {
          latitude: active.location.latitude,
          longitude: active.location.longitude,
        }
      : null;
  // OSRM route/ETA (free, no key). Debounced by tick; null → straight line.
  // No setState-on-clear: when there is no active session the UI ignores
  // stale osrm (distanceLabel + route both gate on `active`).
  const [osrm, setOsrm] = useState<{
    polyline: LatLon[];
    distanceM: number;
    durationS: number;
  } | null>(null);
  useEffect(() => {
    if (!origin || !destination || !active) return;
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      void fetchRoute(origin, destination, ctrl.signal).then((r) => {
        if (!ctrl.signal.aborted && r) setOsrm(r);
      });
    }, 800);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveFixAt, active?.hospital]);
  const distanceLabel =
    osrm && active
      ? `${formatDistance(osrm.distanceM)} · ETA ${formatEta(osrm.durationS)}`
      : active
        ? `${active.distanceKm.toFixed(1)} km · GPS ${gpsMode === "live" ? "LIVE" : "NO FIX"}`
        : "— · Estimated arrival in —";
  const openExternalNav = () => {
    const to = destination
      ? `&to=${destination.latitude}%2C${destination.longitude}`
      : "";
    const url = `https://www.openstreetmap.org/directions?from=${origin?.latitude ?? ""}%2C${origin?.longitude ?? ""}${to}`;
    void Linking.openURL(url);
  };
  // Offer to notify the saved emergency contacts once per session (never on
  // web — SMS is unavailable there). Fetches lazily; silently skipped when
  // offline/not backend-linked or the saved list is empty.
  const maybeNotifyContacts = () => {
    if (notifiedThisSessionRef.current || Platform.OS === "web") return;
    void (async () => {
      try {
        const contacts = await listContacts();
        if (notifiedThisSessionRef.current || contacts.length === 0) return;
        notifiedThisSessionRef.current = true;
        setNotifyContacts(contacts);
        setDialog("notify");
      } catch {
        /* offline / not backend-linked — nothing to notify */
      }
    })();
  };
  // Prepare an SMS with the live location for the saved contacts. Coords
  // come from a one-shot GPS fix, falling back to the last watched fix and
  // then the session's last known position; the link is included only when
  // real coordinates exist. Never throws — SMS handoff is best-effort.
  const sendNotifySms = async () => {
    const lastKnown = { latitude: location.latitude, longitude: location.longitude };
    let coords = liveFix?.fix
      ? { latitude: liveFix.fix.latitude, longitude: liveFix.fix.longitude }
      : lastKnown;
    try {
      const pos = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      coords = { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
    } catch {
      /* unpermitted/unavailable — keep the last known position */
    }
    const hasFix =
      Number.isFinite(coords.latitude) &&
      Number.isFinite(coords.longitude) &&
      !(coords.latitude === 0 && coords.longitude === 0);
    const url = hasFix
      ? ` Live location: https://www.openstreetmap.org/?mlat=${coords.latitude}&mlon=${coords.longitude}#map=16/${coords.latitude}/${coords.longitude}`
      : "";
    try {
      await SMS.sendSMSAsync(
        notifyContacts.map((contact) => contact.phone),
        `Emergency response in progress via SeedGrant.${url}`,
      );
    } catch {
      /* SMS unavailable or handoff dismissed — silently no-op */
    }
    setDialog(null);
  };
  const start = () => {
    if (startingRef.current) return; // no double-tap: two backendStarts
    startingRef.current = true;
    // A fresh session begins: re-arm the once-per-session emergency-contacts
    // notify prompt (it is set when the prompt is shown, never mid-session).
    notifiedThisSessionRef.current = false;
    // Real backend session first; the local record only mirrors what the
    // backend confirms (plus real GPS fixes) so the UI shows live truth.
    (async () => {
      try {
        if (await isBackendLinked()) {
          // Reuse a reconciled in-progress backend session instead of
          // starting a second one server-side (see mount reconcile above).
          if (backendSessionId) return;
          try {
            const amb = await apiMyAmbulance();
            const s = await backendStart(amb.id, state.ambulance.hospital);
            setBackendSessionId(s.session_id);
          } catch {
            // 409 conflict (the server already has an active session for
            // this driver) or a transient failure: reconcile instead of
            // deadlocking on a stale/absent session id.
            try {
              const cur = await backendCurrent();
              setBackendSessionId(cur.active ? cur.session_id : null);
            } catch {
              setBackendSessionId(null);
            }
          }
        }
      } finally {
        startingRef.current = false;
      }
    })();
    dispatch({
      type: "start",
      now: Date.now(),
      seed: liveFresh
        ? { latitude: liveFresh.latitude, longitude: liveFresh.longitude }
        : undefined,
    });
    setDialog(null);
    maybeNotifyContacts();
  };
  const stop = () => {
    if (backendSessionId) {
      const sid = backendSessionId;
      setBackendSessionId(null);
      setBackendPriority(null);
      // backendStop clears the module-level session id in services/emergency.ts
      // on success; on failure it stays tracked and we re-track it here so
      // logout/unmount cleanup can retry ending the server-side session.
      void backendStop(sid).catch(() => retrackBackendSession(sid));
    }
    dispatch({ type: "stop", now: Date.now() });
    setServerEnded(null);
    setDialog(null);
  };
  // If the app unmounts mid-session (logout tears down the tabs, or the root
  // layout is disposed), end the backend session so it cannot outlive the
  // app. No-op when stop()/logout() already ended it.
  const backendSessionIdRef = useRef(backendSessionId);
  useEffect(() => {
    backendSessionIdRef.current = backendSessionId;
  }, [backendSessionId]);
  useEffect(
    () => () => {
      if (backendSessionIdRef.current) void stopActiveBackendSession();
    },
    [],
  );
  const narrow = width < 350 || fontScale > 1.2;
  return (
    <Page>
      <Header title="Hi, Driver" subtitle="Emergency traffic priority system">
        <View>
          <IconButton
            icon="bell-outline"
            label="Emergency events"
            onPress={() => setDialog("events")}
          />
          {active && (
            <View
              style={{
                position: "absolute",
                top: 8,
                right: 10,
                width: 9,
                height: 9,
                borderRadius: 5,
                backgroundColor: c.red,
              }}
            />
          )}
        </View>
        <Avatar onPress={() => router.navigate("/profile")} />
      </Header>
      <View style={s.hero}>
        <Image source={images.login} style={s.heroCity} resizeMode="cover" />
        <View style={s.sideNote}>
          <Txt style={s.noteText}>
            When a patient{"\n"}is in the ambulance,{"\n"}tap to get traffic
            {"\n"}priority
          </Txt>
          <Icon name="arrow-right-bottom" color="#3C5D87" size={28} />
        </View>
        <View style={s.rightNote}>
          <Heartbeat width={70} />
          <Txt
            muted
            style={{ textAlign: "center", fontSize: 11, lineHeight: 16 }}
          >
            Faster roads{"\n"}for a safer{"\n"}tomorrow
          </Txt>
        </View>
        <View style={[s.halo, active && { backgroundColor: "#FCE8ED" }]}>
          <View style={s.innerHalo}>
            <Pressable
              testID="emergency-control"
              accessibilityRole="button"
              accessibilityLabel={active ? "Stop Emergency" : "START EMERGENCY"}
              onPress={() =>
                active
                  ? state.settings.confirmEmergency
                    ? setDialog("stop")
                    : stop()
                  : state.settings.confirmEmergency
                    ? setDialog("start")
                    : start()
              }
              style={({ pressed }) => ({ opacity: pressed ? 0.8 : 1 })}
            >
              <LinearGradient
                colors={
                  active ? ["#FF5360", "#CD1F2C"] : ["#FF6063", "#E4232D"]
                }
                style={s.emergency}
              >
                <AmbulanceMark size={61} white />
                <Txt style={s.emergencyText}>
                  {active ? "EMERGENCY\nACTIVE" : "START\nEMERGENCY"}
                </Txt>
                <Txt style={{ color: "white", fontSize: 12 }}>
                  {active ? "Tap to stop" : "Tap to start"}
                </Txt>
              </LinearGradient>
            </Pressable>
          </View>
        </View>
        {active && (
          <View style={{ alignSelf: "center", marginTop: 7 }}>
            <Badge
              label={`Emergency Active · ${duration(active.startedAt, now)}`}
              tone="red"
            />
          </View>
        )}
      </View>
      <View style={s.grid}>
        <StatusCard
          narrow={narrow}
          icon="map-marker"
          label="Current Location"
          value={location.area}
          detail={
            location.road ||
            (liveFresh?.accuracy != null
              ? `±${Math.round(liveFresh.accuracy)}m accuracy`
              : "Waiting for a fix")
          }
          onPress={() => setDialog("route")}
        />
        <StatusCard
          narrow={narrow}
          icon="traffic-light"
          label="Nearest Junction"
          value={nearest ? nearest.name : location.junction.name || "—"}
          detail={
            nearest
              ? `${Math.round(nearest.distanceM)}m · approach ${nearest.approach}`
              : "Shows when the backend reports one"
          }
          onPress={() => setDialog("route")}
        />
        <StatusCard
          narrow={narrow}
          icon="broadcast"
          label="Live Tracking"
          value={active ? "Tracking Active" : "Tracking Standby"}
          detail={
            active
              ? "Sharing location with control center"
              : "Starts with your emergency"
          }
          green={!!active}
          onPress={() => setDialog("connection")}
        />
        <StatusCard
          narrow={narrow}
          icon="traffic-light"
          label="Priority Status"
          value={priority}
          detail={
            active
              ? "Traffic signal turning green for your direction"
              : "No priority requested"
          }
          green={!!active}
          onPress={() => setDialog("events")}
        />
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Route to Hospital"
        onPress={() => setDialog("route")}
      >
        <Card style={s.routeCard}>
          <View
            style={{ flex: 1.25, gap: 5, paddingLeft: 12, paddingVertical: 15 }}
          >
            <Row>
              <Icon name="map-marker" color={c.red} size={24} />
              <Txt style={{ fontSize: 11, fontWeight: "600" }}>
                Route to Hospital
              </Txt>
            </Row>
            <Txt style={{ fontSize: 13, fontWeight: "700" }}>
              {active?.hospital ?? state.ambulance.hospital}
            </Txt>
            <Txt muted style={{ fontSize: 10 }}>
              {active ? `Distance: ${distanceLabel}` : "Distance: — | ETA: —"}
            </Txt>
            {active && (
              <Badge
                label={gpsMode === "live" ? "LIVE GPS" : "NO FIX"}
                tone={gpsMode === "live" ? "green" : "muted"}
              />
            )}
          </View>
          <View style={{ flex: 1, overflow: "hidden" }}>
            <LiveRouteMap
              origin={origin}
              destination={destination}
              route={osrm?.polyline}
              height={110}
              active={!!active}
            />
            <View style={s.mapEta}>
              <Txt
                style={{
                  color: c.green,
                  fontSize: 11,
                  lineHeight: 15,
                  fontWeight: "700",
                  textAlign: "center",
                }}
              >
                ETA{"\n"}
                {osrm
                  ? formatEta(osrm.durationS)
                  : active
                    ? `${active.distanceKm.toFixed(1)} km`
                    : "—"}
              </Txt>
            </View>
          </View>
        </Card>
      </Pressable>
      <SectionTitle
        action={
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="See all quick actions"
            onPress={() => router.navigate("/history")}
          >
            <Txt style={{ color: c.blue, fontSize: 14, fontWeight: "600" }}>
              See All
            </Txt>
          </Pressable>
        }
      >
        Quick Actions
      </SectionTitle>
      <Row style={{ alignItems: "stretch", gap: 8 }}>
        {(
          [
            {
              title: "Patient Info",
              note: "View / Update",
              icon: "account-plus",
              bg: "#FFF0F2",
              color: c.red,
              onPress: () => setDialog("patient"),
            },
            {
              title: "Navigation",
              note: "Open Maps",
              icon: "navigation",
              bg: c.blueLight,
              color: c.blue,
              onPress: () => (origin ? openExternalNav() : setDialog("route")),
            },
            {
              title: "Trip History",
              note: "Past Trips",
              icon: "history",
              bg: c.greenLight,
              color: c.green,
              onPress: () => router.navigate("/history"),
            },
            {
              title: "Emergency Logs",
              note: "View Records",
              icon: "file-document",
              bg: c.purpleLight,
              color: c.purple,
              onPress: () => setDialog("events"),
            },
          ] as const
        ).map((item) => (
          <Pressable
            key={item.title}
            onPress={item.onPress}
            accessibilityRole="button"
            style={[s.quick, { backgroundColor: item.bg }]}
          >
            <Icon name={item.icon} size={30} color={item.color} />
            <Txt
              style={{
                fontWeight: "600",
                fontSize: 11,
                textAlign: "center",
                lineHeight: 16,
              }}
            >
              {item.title}
            </Txt>
            <Txt muted style={{ fontSize: 10, textAlign: "center" }}>
              {item.note}
            </Txt>
          </Pressable>
        ))}
      </Row>
      <Row style={{ justifyContent: "center" }}>
        <Icon name="shield-check-outline" size={13} color={c.muted} />
        <Txt muted style={{ fontSize: 10 }}>
          {!linked
            ? "Backend not linked — location stays on this device"
            : backendDriving && !gpsUsable
              ? "Backend linked · Weak GPS — waiting for a usable fix"
              : backendDriving && backendError
                ? "Backend linked · Live GPS · connection issues, retrying"
                : backendDriving
                  ? "Backend linked · Live GPS"
                  : "Backend linked"}
        </Txt>
      </Row>
      <Sheet
        visible={!!dialog}
        title={
          dialog === "route"
            ? "Route to Hospital"
            : dialog === "events"
              ? "Emergency Events"
              : dialog === "connection"
                ? "Control Center Connection"
                : dialog === "start"
                  ? "Start Emergency?"
                  : dialog === "ended"
                    ? "Emergency Ended"
                    : dialog === "patient"
                      ? "Patient Handoff"
                      : dialog === "hospital"
                        ? "Destination Hospital"
                        : dialog === "notify"
                          ? "Notify Emergency Contacts?"
                          : "Stop Emergency?"
        }
        onClose={() => setDialog(null)}
      >
        {dialog === "route" && (
          <>
            <LiveRouteMap
              origin={origin}
              destination={destination}
              route={osrm?.polyline}
              height={230}
              active={!!active}
            />
            <Txt style={{ fontSize: 19, fontWeight: "700" }}>
              {active?.hospital ?? state.ambulance.hospital}
            </Txt>
            <Txt muted>
              {active ? distanceLabel : "— · Estimated arrival in —"}
            </Txt>
            <Card>
              <Txt>
                {location.area} · {location.road}
              </Txt>
              <Txt muted>
                {location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}
                {liveFresh?.accuracy != null
                  ? ` · ±${Math.round(liveFresh.accuracy)}m`
                  : ""}
                {liveFresh?.speed != null
                  ? ` · ${liveFresh.speed.toFixed(1)} m/s`
                  : ""}
                {liveFix
                  ? ` · ${Math.round((now - liveFix.at) / 1000)}s ago`
                  : ""}
              </Txt>
              <Txt style={{ marginTop: 10 }}>
                Next:{" "}
                {nearest
                  ? `${nearest.name} · approach ${nearest.approach} · ${Math.round(nearest.distanceM)}m`
                  : location.junction.name || "waiting for backend data"}
              </Txt>
            </Card>
            <Txt muted>
              {gpsMode === "live"
                ? "Live GPS + OSRM route. No data is fabricated."
                : "Waiting for GPS — showing last known position."}
            </Txt>
            <Button
              title="Open in Maps"
              tone="quiet"
              onPress={openExternalNav}
            />
            <Button
              title="Change Hospital"
              tone="quiet"
              onPress={() => setDialog("hospital")}
            />
          </>
        )}
        {dialog === "events" &&
          (active ? (
            <>
              <Badge label="Emergency Active" tone="red" />
              <EventTimeline events={active.events} expanded />
            </>
          ) : (
            <>
              <Txt muted>
                Start an emergency to see live priority events here.
              </Txt>
              <Button
                title="View History"
                tone="quiet"
                onPress={() => {
                  setDialog(null);
                  router.navigate("/history");
                }}
              />
            </>
          ))}
        {dialog === "connection" && (
          <>
            <Badge
              label={
                backendDriving
                  ? `Connected · ${gpsMode === "live" ? "LIVE" : "NO FIX"}${bgMode === "started" ? " + BG" : ""}`
                  : active
                    ? "Not linked · Local only"
                    : "Ready"
              }
            />
            <Txt>{state.ambulance.controlCenter}</Txt>
            <Txt muted>
              {backendDriving
                ? `Session ${backendSessionId} · ${gpsMode === "live" ? `accuracy ±${Math.round(liveFresh?.accuracy ?? 0)}m` : "waiting for fix"}${lastLatencyMs != null ? ` · ${lastLatencyMs}ms` : ""}${queuedCount > 0 ? ` · ${queuedCount} queued` : ""}${backendError ? " · retrying" : ""}`
                : active
                  ? "Backend not linked — fixes stay on this device and no priority is requested."
                  : "Live tracking starts when you activate an emergency."}
            </Txt>
            <Txt muted>
              {bgMode === "started"
                ? "Background tracking active — fixes keep posting when the app is backgrounded."
                : "Foreground fixes every ~2-3s. Background tracking starts when permitted."}
            </Txt>
          </>
        )}
        {(dialog === "start" || dialog === "stop") && (
          <>
            <Txt>
              {dialog === "start"
                ? "Begin live tracking and request traffic signal priority for your route."
                : "End this emergency, release priority, and save the session to History."}
            </Txt>
            <Button
              title={dialog === "start" ? "Start Emergency" : "Stop Emergency"}
              tone="red"
              onPress={dialog === "start" ? start : stop}
            />
            <Button
              title="Cancel"
              tone="quiet"
              onPress={() => setDialog(null)}
              icon="close"
            />
          </>
        )}
        {dialog === "ended" && (
          <>
            <Badge label={`Session ${serverEnded ?? "ENDED"}`} tone="red" />
            <Txt>
              The control center reports this emergency as {serverEnded}. The
              session was ended on this device and saved to History.
            </Txt>
            <Button title="Close" tone="red" onPress={() => setDialog(null)} />
          </>
        )}
        {dialog === "hospital" && (
          <>
            {hospitalOptions.length === 0 ? (
              <Txt muted>
                No hospital list from backend — destination stays free text:{" "}
                {active?.hospital ?? state.ambulance.hospital}
              </Txt>
            ) : (
              hospitalOptions.map((h) => (
                <Button
                  key={h.id}
                  title={h.name}
                  tone="quiet"
                  onPress={() => {
                    dispatch({
                      type: "ambulance",
                      patch: { hospital: h.name },
                    });
                    setDialog("route");
                  }}
                />
              ))
            )}
            <Button
              title="Back"
              tone="quiet"
              onPress={() => setDialog("route")}
            />
          </>
        )}
        {dialog === "patient" && (
          <>
            <Txt muted>
              Handoff notes are posted to the active backend session (best
              effort) and never block the emergency.
            </Txt>
            <Field
              label="Patient notes"
              value={patientNotes}
              onChangeText={setPatientNotes}
              placeholder="Age, condition, vitals…"
            />
            <Field
              label="Severity (stable / urgent / critical)"
              value={patientSeverity}
              onChangeText={setPatientSeverity}
            />
            <Button
              title={
                backendSessionId ? "Send Handoff" : "No Active Backend Session"
              }
              tone="red"
              onPress={() => {
                if (backendSessionId)
                  void backendPatient(backendSessionId, {
                    notes: patientNotes,
                    severity: patientSeverity,
                  }).catch(() => undefined);
                setDialog(null);
              }}
            />
            <Button
              title="Close"
              tone="quiet"
              onPress={() => setDialog(null)}
            />
          </>
        )}
        {dialog === "notify" && (
          <>
            <Txt>Notify your emergency contacts about this response?</Txt>
            <Txt style={{ fontWeight: "600" }}>
              {notifyContacts.map((contact) => contact.name).join(", ")}
            </Txt>
            <Txt muted>
              An SMS with your live location will be prepared for each contact —
              you confirm sending in your messaging app.
            </Txt>
            <Button
              title="Send SMS"
              tone="red"
              icon="message-text"
              onPress={() => void sendNotifySms()}
            />
            <Button
              title="Not now"
              tone="quiet"
              icon="close"
              onPress={() => setDialog(null)}
            />
          </>
        )}
      </Sheet>
    </Page>
  );
}
const s = StyleSheet.create({
  hero: {
    minHeight: 195,
    marginHorizontal: -16,
    marginTop: -5,
    paddingBottom: 14,
    alignItems: "center",
  },
  heroCity: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    width: "100%",
    height: 130,
    opacity: 0.19,
  },
  halo: {
    width: 205,
    height: 205,
    borderRadius: 110,
    backgroundColor: "#FFEEEEB0",
    alignItems: "center",
    justifyContent: "center",
  },
  innerHalo: {
    width: 178,
    height: 178,
    borderRadius: 95,
    backgroundColor: "#FFB8BCCC",
    alignItems: "center",
    justifyContent: "center",
  },
  emergency: {
    height: 156,
    width: 156,
    borderRadius: 85,
    borderWidth: 3,
    borderColor: "#FF8C90",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    shadowColor: "#EF2C3B",
    shadowOpacity: 0.28,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 4 },
    elevation: 7,
  },
  emergencyText: {
    fontSize: 18,
    fontWeight: "700",
    lineHeight: 21,
    color: "white",
    textAlign: "center",
  },
  sideNote: {
    position: "absolute",
    left: 16,
    top: 50,
    maxWidth: "24%",
    alignItems: "flex-end",
  },
  noteText: {
    fontSize: 10,
    lineHeight: 15,
    fontStyle: "italic",
    color: "#34547C",
    transform: [{ rotate: "-6deg" }],
  },
  rightNote: {
    position: "absolute",
    right: 8,
    top: 44,
    maxWidth: "22%",
    alignItems: "center",
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    justifyContent: "space-between",
  },
  status: {
    flexDirection: "row",
    alignItems: "center",
    padding: 11,
    gap: 8,
    minHeight: 98,
  },
  routeCard: { padding: 0, overflow: "hidden", flexDirection: "row", gap: 4 },
  mapEta: {
    position: "absolute",
    bottom: 8,
    right: 8,
    backgroundColor: "#E3FAF0",
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 7,
    alignItems: "center",
  },
  quick: {
    flex: 1,
    paddingVertical: 16,
    paddingHorizontal: 5,
    borderRadius: 13,
    alignItems: "center",
    gap: 5,
  },
});
