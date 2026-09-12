/**
 * HOSPITAL Live Tracking (plan §4.2) — split view: the hospital's active
 * emergency sessions on the left, their latest GPS on the map on the right.
 * Selecting a session opens a Drawer with the command timeline and status.
 * Polls /admin/live every 10s (server scopes to own hospital).
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { useLocation } from "react-router-dom";
import {
  Badge,
  Card,
  Drawer,
  Empty,
  PageHeader,
  SectionTitle,
  Timeline,
  Txt,
} from "@/components/ui";
import { fetchLive } from "@/services/portal";
import type { LiveSession } from "@/types/portal";
import { Loading, InlineError } from "@/pages/shared/bits";
import { MapView, type MapDot } from "@/pages/shared/MapView";
import {
  DEFAULT_CENTER,
  fmtDateTime,
  fmtElapsed,
  fmtRelative,
  statusBadgeTone,
  timelineTone,
  toneColor,
} from "@/pages/shared/format";

const LIVE_REFRESH = 10_000;

export function HospitalLiveTrackingPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "HOSPITAL") as PortalRole);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const live = useQuery({
    queryKey: ["live"],
    queryFn: fetchLive,
    refetchInterval: LIVE_REFRESH,
  });

  const sessions = live.data?.items ?? [];
  const selected: LiveSession | null =
    sessions.find((s) => s.id === selectedId) ?? null;

  const dots: MapDot[] = sessions
    .filter((s) => s.latest_gps)
    .map((s) => ({
      id: s.id,
      latitude: s.latest_gps!.latitude,
      longitude: s.latest_gps!.longitude,
      color: toneColor(statusBadgeTone(s.status)),
      title: s.ambulance.vehicle_no,
      detail: `${s.driver.email} · ${s.status}`,
    }));
  const firstDot = dots[0];

  return (
    <div className="page-body">
      <PageHeader
        title="Live Tracking"
        subtitle={item?.subtitle ?? "Your active emergencies and live positions"}
      />

      {live.error && <InlineError error={live.error} fallback="Could not load live sessions." />}

      {live.isLoading ? (
        <Loading label="Loading live sessions" />
      ) : sessions.length === 0 ? (
        <Empty
          icon="my_location"
          title="No active emergencies"
          body="Live positions and priority state appear here while one of your ambulances is in an emergency."
        />
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(300px, 380px) 1fr",
            gap: 14,
            alignItems: "start",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {sessions.map((session) => {
              const isSelected = session.id === selectedId;
              return (
                <div
                  key={session.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedId(session.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedId(session.id);
                    }
                  }}
                  style={{
                    cursor: "pointer",
                    borderRadius: "var(--radius-card)",
                    outline: isSelected ? "2px solid var(--blue)" : undefined,
                  }}
                >
                  <Card style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 8,
                      }}
                    >
                      <Txt style={{ fontWeight: 700, fontSize: 16 }}>
                        {session.ambulance.vehicle_no}
                      </Txt>
                      <Badge
                        label={session.status}
                        tone={statusBadgeTone(session.status)}
                      />
                    </div>
                    <Txt muted>{session.driver.email}</Txt>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        gap: 8,
                        flexWrap: "wrap",
                      }}
                    >
                      <Txt muted>started {fmtRelative(session.started_at)}</Txt>
                      <Txt>elapsed {fmtElapsed(session.started_at)}</Txt>
                    </div>
                    {session.latest_gps && (
                      <Txt muted style={{ fontSize: 12 }}>
                        last GPS {fmtRelative(session.latest_gps.recorded_at)} ·{" "}
                        {session.latest_gps.latitude.toFixed(5)},{" "}
                        {session.latest_gps.longitude.toFixed(5)}
                      </Txt>
                    )}
                  </Card>
                </div>
              );
            })}
          </div>

          <MapView
            ariaLabel="Live positions of your ambulances"
            dots={dots}
            center={
              firstDot ? [firstDot.latitude, firstDot.longitude] : DEFAULT_CENTER
            }
            height={520}
          />
        </div>
      )}

      <Drawer
        open={selected !== null}
        title={selected ? selected.ambulance.vehicle_no : "Session"}
        onClose={() => setSelectedId(null)}
      >
        {selected && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <Badge label={selected.status} tone={statusBadgeTone(selected.status)} />
              <Txt muted>started {fmtDateTime(selected.started_at)}</Txt>
              <Txt>elapsed {fmtElapsed(selected.started_at)}</Txt>
            </div>

            <Card style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <Txt muted style={{ fontSize: 12, textTransform: "uppercase", fontWeight: 600 }}>
                Driver
              </Txt>
              <Txt>{selected.driver.email}</Txt>
              <Txt muted style={{ fontSize: 12, textTransform: "uppercase", fontWeight: 600 }}>
                Ambulance
              </Txt>
              <Txt>{selected.ambulance.vehicle_no}</Txt>
              {selected.latest_gps && (
                <>
                  <Txt muted style={{ fontSize: 12, textTransform: "uppercase", fontWeight: 600 }}>
                    Last GPS
                  </Txt>
                  <Txt>
                    {selected.latest_gps.latitude.toFixed(5)},{" "}
                    {selected.latest_gps.longitude.toFixed(5)} ·{" "}
                    {fmtRelative(selected.latest_gps.recorded_at)}
                  </Txt>
                </>
              )}
            </Card>

            <SectionTitle>Priority Commands</SectionTitle>
            {selected.commands.length === 0 ? (
              <Txt muted>
                No priority commands issued for this session yet.
              </Txt>
            ) : (
              <Timeline
                items={selected.commands.map((command) => ({
                  title: `${command.type}${command.approach ? ` · ${command.approach}` : ""}`,
                  meta: command.status,
                  tone: timelineTone(command.status),
                }))}
              />
            )}
          </>
        )}
      </Drawer>
    </div>
  );
}
