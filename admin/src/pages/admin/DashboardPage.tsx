/**
 * ADMIN Dashboard (plan §4.1) — live system KPIs plus the active session feed.
 * Stats: active emergencies (/admin/live), fleet size (/ambulances),
 * devices online (/admin/devices/status) and pending+sent commands
 * (/admin/analytics/overview). Polls the operational endpoints every 10s.
 */

import { useQuery } from "@tanstack/react-query";
import {
  fetchAnalytics,
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
import "@/pages/admin/admin.css";

export function DashboardPage() {
  const live = useQuery({
    queryKey: ["admin", "live"],
    queryFn: fetchLive,
    refetchInterval: 10_000,
  });
  const fleet = useQuery({
    queryKey: ["admin", "ambulances"],
    queryFn: listAmbulances,
  });
  const devices = useQuery({
    queryKey: ["admin", "devices"],
    queryFn: listDevices,
    refetchInterval: 10_000,
  });
  const analytics = useQuery({
    queryKey: ["admin", "analytics", 7],
    queryFn: () => fetchAnalytics(7),
  });

  const sessions = live.data?.items ?? [];
  const online = devices.data?.filter((d) => d.online).length ?? null;
  const pending = analytics.data
    ? (analytics.data.commands.by_status["PENDING"] ?? 0) +
      (analytics.data.commands.by_status["SENT"] ?? 0)
    : null;

  return (
    <div className="page-body">
      <PageHeader
        title="Dashboard"
        subtitle="System overview across all junctions, fleets and devices"
      />

      <div className="stat-grid">
        <StatCard
          label="Active Emergencies"
          value={live.isError ? "—" : String(sessions.length)}
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

      <SectionTitle>Active sessions</SectionTitle>
      {live.isLoading ? (
        <LoadingBlock label="Loading active sessions" />
      ) : live.isError ? (
        <ErrorCard
          title="Could not load active sessions"
          error={live.error}
          onRetry={() => void live.refetch()}
        />
      ) : sessions.length === 0 ? (
        <Empty
          icon="emergency"
          title="No active sessions"
          body="When a driver starts an emergency it appears here within seconds."
        />
      ) : (
        <Card style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {sessions.map((s) => (
            <div
              key={s.id}
              className="admin-session-row"
              style={{ cursor: "default" }}
            >
              <Badge label={s.status} tone={statusTone(s.status)} />
              <span className="admin-session-main">
                <Txt style={{ fontWeight: 600 }}>{s.ambulance.vehicle_no}</Txt>
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
      )}
    </div>
  );
}
