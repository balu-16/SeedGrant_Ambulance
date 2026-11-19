/**
 * ADMIN Dashboard (plan §4.1) — live system KPIs plus the active session feed
 * and the latest alerts. Stats: active emergencies (/admin/live uncapped
 * total), fleet size (/ambulances), devices online (/admin/devices/status) and
 * the current pending-command count computed from the live feed's open
 * commands (PENDING/SENT — contract §5/§9, not the historical analytics
 * window). Polls the operational endpoints every 10s.
 */

import { useQuery } from "@tanstack/react-query";
import {
  fetchAlerts,
  fetchLive,
  listAmbulances,
  listDevices,
} from "@/services/portal";
import { statusTone } from "@/components/helpers";
import {
  Badge,
  Card,
  Empty,
  PageHeader,
  SectionTitle,
  StatCard,
  Txt,
} from "@/components/ui";
import { fmtDateTime } from "@/pages/admin/shared";
import { ErrorCard, LoadingBlock } from "@/pages/admin/widgets";
import { FreshnessCaption, StaleBanner } from "@/pages/shared/bits";
import { isStale, useFreshnessThresholds } from "@/pages/shared/freshness";
import { fmtRelative, severityTone } from "@/pages/shared/format";
import "@/pages/admin/admin.css";

const LIVE_REFRESH = 10_000;

export function DashboardPage() {
  const thresholds = useFreshnessThresholds();
  const live = useQuery({
    queryKey: ["admin", "live"],
    queryFn: fetchLive,
    refetchInterval: LIVE_REFRESH,
  });
  const fleet = useQuery({
    queryKey: ["admin", "ambulances"],
    queryFn: listAmbulances,
  });
  const devices = useQuery({
    queryKey: ["admin", "devices"],
    queryFn: listDevices,
    refetchInterval: LIVE_REFRESH,
  });
  const alerts = useQuery({
    queryKey: ["admin", "alerts", 5],
    queryFn: () => fetchAlerts(5),
    refetchInterval: LIVE_REFRESH,
  });

  const sessions = live.data?.items ?? [];
  const online = devices.data?.filter((d) => d.online).length ?? null;
  // Current pending commands from the live snapshot (PENDING/SENT commands
  // across active sessions) — contract §9, not the analytics window.
  const pending = live.data
    ? sessions.reduce(
        (n, s) =>
          n +
          s.commands.filter((c) => {
            const st = c.status.toUpperCase();
            return st === "PENDING" || st === "SENT";
          }).length,
        0,
      )
    : null;
  const activeTotal = live.data ? live.data.total ?? sessions.length : null;
  const stale =
    live.data !== undefined &&
    isStale(live.dataUpdatedAt, thresholds.portalStaleSeconds);

  return (
    <div className="page-body">
      <PageHeader
        title="Dashboard"
        subtitle="System overview across all junctions, fleets and devices"
      />

      {live.isError && (
        <ErrorCard
          title="Could not load live sessions"
          error={live.error}
          onRetry={() => void live.refetch()}
        />
      )}
      <StaleBanner stale={stale} />

      <div className="stat-grid">
        <StatCard
          label="Active Emergencies"
          value={activeTotal !== null ? String(activeTotal) : "—"}
          tone="red"
          icon="emergency"
        />
        <StatCard
          label="Fleet"
          value={fleet.data ? String(fleet.data.length) : "—"}
          tone="blue"
          icon="local_shipping"
        />
        <StatCard
          label="Devices Online"
          value={
            devices.data && online !== null
              ? `${online} / ${devices.data.length}`
              : "—"
          }
          tone="green"
          icon="memory"
        />
        <StatCard
          label="Pending Commands"
          value={pending !== null ? String(pending) : "—"}
          tone="purple"
          icon="terminal"
        />
      </div>

      <SectionTitle
        action={
          live.data ? (
            <FreshnessCaption updatedAt={live.dataUpdatedAt} />
          ) : undefined
        }
      >
        Active sessions
      </SectionTitle>
      {live.isPending && !live.data ? (
        <LoadingBlock label="Loading active sessions" />
      ) : live.data ? (
        sessions.length === 0 ? (
          <Empty
            icon="emergency"
            title="No active sessions"
            body="When a driver starts an emergency it appears here within seconds."
          />
        ) : (
          <>
            <Card style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {sessions.map((s) => (
                <div
                  key={s.id}
                  className="admin-session-row"
                  style={{ cursor: "default" }}
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
                  <Txt muted className="admin-mono">
                    {fmtDateTime(s.started_at)}
                  </Txt>
                </div>
              ))}
            </Card>
            {live.data.total > sessions.length && live.data.cap > 0 && (
              <Txt muted>
                Showing the {sessions.length} most recent of {live.data.total}{" "}
                active sessions (list cap {live.data.cap}).
              </Txt>
            )}
          </>
        )
      ) : !live.isError ? (
        <Empty
          icon="emergency"
          title="No active sessions"
          body="When a driver starts an emergency it appears here within seconds."
        />
      ) : null}

      <SectionTitle
        action={
          alerts.data && alerts.data.length > 0 ? (
            <Txt muted style={{ fontSize: 12 }}>
              latest {alerts.data.length}
            </Txt>
          ) : undefined
        }
      >
        Latest alerts
      </SectionTitle>
      {alerts.isError ? (
        <ErrorCard
          title="Could not load alerts"
          error={alerts.error}
          onRetry={() => void alerts.refetch()}
        />
      ) : alerts.isPending ? (
        <LoadingBlock label="Loading alerts" />
      ) : (alerts.data ?? []).length === 0 ? (
        <Empty
          icon="notifications_active"
          title="No alerts"
          body="Emergency starts and endings, timed-out sessions, expired commands and offline devices appear here."
        />
      ) : (
        <Card style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {(alerts.data ?? []).map((alert, i) => (
            <div
              key={`${alert.at}-${i}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                flexWrap: "wrap",
              }}
            >
              <Badge label={alert.severity} tone={severityTone(alert.severity)} />
              <Txt style={{ flex: 1, minWidth: 200 }}>{alert.message}</Txt>
              <Txt muted>{fmtRelative(alert.at)}</Txt>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
