/**
 * HOSPITAL Dashboard (plan §4.2) — the fleet at a glance: active emergencies,
 * fleet size, on-duty ambulances and average emergency duration, then the
 * active sessions and the latest scoped alerts. All queries are scoped to the
 * signed-in hospital server-side; live numbers poll every 10s.
 */

import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import {
  Badge,
  Card,
  Empty,
  PageHeader,
  SectionTitle,
  StatCard,
  Txt,
} from "@/components/ui";
import { fetchAlerts, fetchLive, fetchAnalytics, listAmbulances } from "@/services/portal";
import { Loading, InlineError } from "@/pages/shared/bits";
import { fmtElapsed, fmtRelative, severityTone, statusBadgeTone } from "@/pages/shared/format";

const LIVE_REFRESH = 10_000;

export function HospitalDashboardPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "HOSPITAL") as PortalRole);

  const live = useQuery({
    queryKey: ["live"],
    queryFn: fetchLive,
    refetchInterval: LIVE_REFRESH,
  });
  const fleet = useQuery({ queryKey: ["ambulances"], queryFn: listAmbulances });
  const analytics = useQuery({ queryKey: ["analytics", 7], queryFn: () => fetchAnalytics(7) });
  const alerts = useQuery({
    queryKey: ["alerts", 5],
    queryFn: () => fetchAlerts(5),
    refetchInterval: LIVE_REFRESH,
  });

  const sessions = live.data?.items ?? [];
  const ambulances = fleet.data ?? [];
  const onDuty = ambulances.filter((a) => a.on_duty).length;
  const avgDuration = analytics.data?.emergencies.avg_duration_minutes ?? null;

  return (
    <div className="page-body">
      <PageHeader
        title="Dashboard"
        subtitle={item?.subtitle ?? "Your fleet at a glance"}
      />

      {(live.error || fleet.error || analytics.error) && (
        <InlineError
          error={live.error ?? fleet.error ?? analytics.error}
          fallback="Could not load dashboard numbers."
        />
      )}

      <div className="stat-grid">
        <StatCard
          label="Active Emergencies"
          value={live.isLoading ? "…" : String(sessions.length)}
          tone="red"
          icon="emergency"
        />
        <StatCard
          label="Fleet Size"
          value={fleet.isLoading ? "…" : String(ambulances.length)}
          tone="blue"
          icon="local_shipping"
        />
        <StatCard
          label="On-Duty"
          value={fleet.isLoading ? "…" : String(onDuty)}
          tone="green"
          icon="engineering"
        />
        <StatCard
          label="Avg Duration"
          value={
            analytics.isLoading
              ? "…"
              : avgDuration === null
                ? "—"
                : `${Math.round(avgDuration)} min`
          }
          tone="purple"
          icon="timer"
        />
      </div>

      <SectionTitle>Active Sessions</SectionTitle>
      {live.isLoading ? (
        <Loading label="Loading active sessions" />
      ) : sessions.length === 0 ? (
        <Empty
          icon="event_available"
          title="No active emergencies"
          body="When one of your ambulances starts an emergency, the live session appears here."
        />
      ) : (
        <Card style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {sessions.map((session) => (
            <div
              key={session.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                flexWrap: "wrap",
              }}
            >
              <Txt style={{ fontWeight: 700, minWidth: 110 }}>
                {session.ambulance.vehicle_no}
              </Txt>
              <Badge label={session.status} tone={statusBadgeTone(session.status)} />
              <Txt muted style={{ flex: 1, minWidth: 160 }}>
                {session.driver.email}
              </Txt>
              <Txt muted>started {fmtRelative(session.started_at)}</Txt>
              <Txt>{fmtElapsed(session.started_at)}</Txt>
            </div>
          ))}
        </Card>
      )}

      <SectionTitle
        action={
          <Link to="/alerts" style={{ fontSize: 13, fontWeight: 600 }}>
            View all
          </Link>
        }
      >
        Latest Alerts
      </SectionTitle>
      {alerts.isLoading ? (
        <Loading label="Loading alerts" />
      ) : (alerts.data ?? []).length === 0 ? (
        <Empty
          icon="notifications_off"
          title="No alerts"
          body="Timeouts, device-offline events and emergency alerts for your fleet appear here."
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
