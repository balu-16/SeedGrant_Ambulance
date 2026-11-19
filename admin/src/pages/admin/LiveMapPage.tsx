/**
 * ADMIN Live Map (plan §4.1) — junction markers (blue) and active sessions'
 * latest GPS (red, pulsing) on OpenStreetMap tiles; clicking a session marker
 * or list row opens the right drawer with session info, its command timeline
 * and a small static map of the latest fix. Live data polls every 10s.
 *
 * Freshness (contract §9): "Last updated Xs ago" caption, stale banner past
 * portal_stale_seconds, "Stale GPS" badge past gps_stale_seconds, junction
 * signal state renders "Unknown" when the latest telemetry has no state, and
 * a failed refetch keeps the previous data with an error banner (never an
 * empty/zero state).
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import * as L from "leaflet";
import { MapContainer, Marker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import { fetchLive, listJunctions } from "@/services/portal";
import type { LiveSession } from "@/types/portal";
import { tileUrl } from "@/pages/shared/format";
import { statusTone } from "@/components/helpers";
import {
  Badge,
  Card,
  Drawer,
  Empty,
  Icon,
  PageHeader,
  SectionTitle,
  Timeline,
  Txt,
} from "@/components/ui";
import { fmtAgo, fmtDateTime, shortId, timelineTone } from "@/pages/admin/shared";
import { ErrorCard, KVList, LoadingBlock } from "@/pages/admin/widgets";
import { TileLayerGuard } from "@/pages/shared/MapView";
import {
  FreshnessCaption,
  GpsStaleBadge,
  StaleBanner,
} from "@/pages/shared/bits";
import { isStale, useFreshnessThresholds } from "@/pages/shared/freshness";
import "@/pages/admin/admin.css";

const OSM_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
// Self-host tiles in production: set VITE_TILES_URL to your tile server.
// Defaults to public OSM (rate-limited) for dev.
const OSM_URL = tileUrl();
// Shared India fallback (same as pages/shared/format DEFAULT_CENTER source).
// Junctions/sessions with real coords recenter the map; this is last resort.
const DEFAULT_CENTER: [number, number] = [20.5937, 78.9629];

const junctionIcon = L.divIcon({
  className: "admin-pin",
  html: '<span class="admin-dot admin-dot--blue"></span>',
  iconSize: [14, 14],
  iconAnchor: [7, 7],
});

const sessionIcon = L.divIcon({
  className: "admin-pin",
  html: '<span class="admin-dot admin-dot--red admin-dot--pulse"></span>',
  iconSize: [14, 14],
  iconAnchor: [7, 7],
});

/** Re-centres the map when the data-driven view target changes. */
function Recenter({ lat, lng, zoom }: { lat: number; lng: number; zoom: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView([lat, lng], zoom);
  }, [map, lat, lng, zoom]);
  return null;
}

export function LiveMapPage() {
  const thresholds = useFreshnessThresholds();
  const junctions = useQuery({
    queryKey: ["admin", "junctions"],
    queryFn: listJunctions,
  });
  const live = useQuery({
    queryKey: ["admin", "live"],
    queryFn: fetchLive,
    refetchInterval: 10_000,
    placeholderData: keepPreviousData,
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const liveItems = live.data?.items;
  const junctionData = junctions.data;
  const sessions = useMemo(() => liveItems ?? [], [liveItems]);
  const junctionItems = useMemo(() => junctionData ?? [], [junctionData]);
  const junctionStates = live.data?.junction_states ?? {};
  const selected = sessions.find((s) => s.id === selectedId) ?? null;
  const stale =
    live.data !== undefined &&
    isStale(live.dataUpdatedAt, thresholds.portalStaleSeconds);

  const center = useMemo<[number, number]>(() => {
    const withFix = sessions.find((s) => s.latest_gps !== null);
    if (withFix?.latest_gps) {
      return [withFix.latest_gps.latitude, withFix.latest_gps.longitude];
    }
    const withCoords = junctionItems.find(
      (j) => j.latitude != null && j.longitude != null,
    );
    if (withCoords?.latitude != null && withCoords.longitude != null) {
      return [withCoords.latitude, withCoords.longitude];
    }
    return DEFAULT_CENTER;
  }, [sessions, junctionItems]);
  const zoom = center === DEFAULT_CENTER ? 5 : 13;

  return (
    <div className="page-body">
      <PageHeader
        title="Live Map"
        subtitle="Active emergencies and junction states on one map"
      />

      {/* A failed refetch keeps the previous map + list and shows a banner. */}
      {live.isError && (
        <ErrorCard
          title="Could not refresh live sessions — showing the last loaded positions"
          error={live.error}
          onRetry={() => void live.refetch()}
        />
      )}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
          flexWrap: "wrap",
        }}
      >
        {live.data && (
          <Txt muted>
            {live.data.total > sessions.length && live.data.cap > 0
              ? `Showing ${sessions.length} of ${live.data.total} active sessions (cap ${live.data.cap}) · `
              : `${sessions.length} active session${sessions.length === 1 ? "" : "s"} · `}
            observed {fmtAgo(live.data.observed_at)}
          </Txt>
        )}
        <FreshnessCaption updatedAt={live.dataUpdatedAt} />
      </div>
      <StaleBanner stale={stale} />

      <div className="admin-map-grid">
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <SectionTitle>Sessions ({sessions.length})</SectionTitle>
          {live.isPending && !live.data ? (
            <LoadingBlock label="Loading sessions" />
          ) : sessions.length === 0 && !live.isError ? (
            <Empty
              icon="emergency"
              title="No active sessions"
              body="Emergency positions appear here as soon as drivers report GPS."
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {sessions.map((s) => (
                <button
                  type="button"
                  key={s.id}
                  className={`admin-session-row${
                    selectedId === s.id ? " admin-session-row--active" : ""
                  }`}
                  onClick={() => setSelectedId(s.id)}
                >
                  <Badge label={s.status} tone={statusTone(s.status)} />
                  <span className="admin-session-main">
                    <Txt style={{ fontWeight: 600 }}>
                      {s.ambulance.vehicle_no}
                    </Txt>
                    <Txt muted className="admin-clamp">
                      {s.driver.email}
                    </Txt>
                  </span>
                  <Icon name="chevron_right" size={18} color="var(--muted)" />
                </button>
              ))}
            </div>
          )}

          {Object.keys(junctionStates).length > 0 && (
            <Card>
              <Txt as="div" style={{ fontWeight: 600, marginBottom: 6 }}>
                Junctions
              </Txt>
              {Object.entries(junctionStates).map(([jid, state]) => (
                <div
                  key={jid}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    flexWrap: "wrap",
                    padding: "5px 0",
                  }}
                >
                  <Txt style={{ flex: 1, minWidth: 120 }}>{state.name}</Txt>
                  <Badge
                    label={state.online ? "ONLINE" : "OFFLINE"}
                    tone={state.online ? "green" : "red"}
                  />
                  {/* Contract §5: telemetry without a state key → "Unknown". */}
                  <Badge
                    label={state.state ?? "Unknown"}
                    tone={state.state ? statusTone(state.state) : "neutral"}
                  />
                </div>
              ))}
            </Card>
          )}

          <Card style={{ marginTop: 2 }}>
            <Txt as="div" style={{ fontWeight: 600, marginBottom: 6 }}>
              Legend
            </Txt>
            <span
              className="admin-session-row"
              style={{ cursor: "default", padding: "8px 10px" }}
            >
              <span className="admin-dot admin-dot--blue" aria-hidden />
              <Txt muted style={{ fontSize: 13 }}>
                Junction
              </Txt>
            </span>
            <span
              className="admin-session-row"
              style={{ cursor: "default", padding: "8px 10px", marginTop: 8 }}
            >
              <span
                className="admin-dot admin-dot--red admin-dot--pulse"
                aria-hidden
              />
              <Txt muted style={{ fontSize: 13 }}>
                Ambulance (latest GPS)
              </Txt>
            </span>
          </Card>
        </div>

        <div className="admin-map-box">
          <MapContainer
            center={center}
            zoom={zoom}
            scrollWheelZoom
            style={{ height: "100%", width: "100%" }}
          >
            <TileLayerGuard attribution={OSM_ATTR} url={OSM_URL} />
            <Recenter lat={center[0]} lng={center[1]} zoom={zoom} />
            {junctionItems.map((j) =>
              j.latitude != null && j.longitude != null ? (
                <Marker
                  key={j.id}
                  position={[j.latitude, j.longitude]}
                  icon={junctionIcon}
                >
                  <Popup>
                    <b>{j.name}</b>
                    {junctionStates[j.id] ? (
                      <>
                        <br />
                        {junctionStates[j.id].online ? "Device online" : "Device offline"}
                        <br />
                        Signal state: {junctionStates[j.id].state ?? "Unknown"}
                      </>
                    ) : null}
                  </Popup>
                </Marker>
              ) : null,
            )}
            {sessions.map((s) =>
              s.latest_gps ? (
                <Marker
                  key={s.id}
                  position={[s.latest_gps.latitude, s.latest_gps.longitude]}
                  icon={sessionIcon}
                  eventHandlers={{ click: () => setSelectedId(s.id) }}
                />
              ) : null,
            )}
          </MapContainer>
        </div>
      </div>

      <Drawer
        open={selected !== null}
        title="Session detail"
        onClose={() => setSelectedId(null)}
        width={480}
      >
        {selected && <SessionDetail session={selected} />}
      </Drawer>
    </div>
  );
}

function SessionDetail({ session }: { session: LiveSession }) {
  const thresholds = useFreshnessThresholds();
  const gps = session.latest_gps;
  return (
    <>
      <Card>
        <KVList
          entries={[
            ["Driver", session.driver.email],
            ["Ambulance", session.ambulance.vehicle_no],
            ["Session", shortId(session.id)],
            ["Started", fmtDateTime(session.started_at)],
          ]}
        />
        <div style={{ marginTop: 12 }}>
          <Badge label={session.status} tone={statusTone(session.status)} />
        </div>
      </Card>

      <Card>
        <Txt as="div" style={{ fontWeight: 600, marginBottom: 8 }}>
          Priority commands
        </Txt>
        {session.commands.length === 0 ? (
          <Txt muted>No commands issued for this session yet.</Txt>
        ) : (
          <Timeline
            items={session.commands.map((c) => ({
              title: `${c.type} · ${c.approach || "all approaches"}`,
              meta: `${c.status} — junction ${shortId(c.junction_id)}`,
              tone: timelineTone(c.status),
            }))}
          />
        )}
        <Txt muted style={{ marginTop: 8 }}>
          Acknowledged = the device received the command, not that the signal
          changed.
        </Txt>
      </Card>

      <Card>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
            marginBottom: 8,
          }}
        >
          <Txt as="div" style={{ fontWeight: 600 }}>
            Latest GPS
          </Txt>
          <GpsStaleBadge
            recordedAt={gps?.recorded_at}
            gpsStaleSeconds={thresholds.gpsStaleSeconds}
          />
        </div>
        {gps ? (
          <>
            <div className="admin-map-box" style={{ height: 170 }}>
              <MapContainer
                center={[gps.latitude, gps.longitude]}
                zoom={15}
                dragging={false}
                scrollWheelZoom={false}
                doubleClickZoom={false}
                touchZoom={false}
                zoomControl={false}
                keyboard={false}
                style={{ height: "100%", width: "100%" }}
              >
                <TileLayerGuard attribution={OSM_ATTR} url={OSM_URL} />
                <Marker
                  position={[gps.latitude, gps.longitude]}
                  icon={sessionIcon}
                />
              </MapContainer>
            </div>
            <Txt muted className="admin-mono" style={{ marginTop: 8 }}>
              lat {gps.latitude.toFixed(5)}, lng {gps.longitude.toFixed(5)} ·{" "}
              {fmtAgo(gps.recorded_at)}
            </Txt>
          </>
        ) : (
          <Txt muted>No GPS fix received for this session yet.</Txt>
        )}
      </Card>
    </>
  );
}
