/**
 * HOSPITAL Alerts (plan §4.2) — scoped alert feed: fleet emergency starts/
 * completions, timeouts and device-offline events. Severity maps to Badge
 * tone (high=red, medium=purple, low=neutral). Polls every 10s.
 */

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { useLocation } from "react-router-dom";
import { Badge, Card, Empty, PageHeader, Txt } from "@/components/ui";
import { fetchAlerts } from "@/services/portal";
import { Loading, InlineError } from "@/pages/shared/bits";
import { fmtDateTime, severityTone } from "@/pages/shared/format";

const LIVE_REFRESH = 10_000;

export function HospitalAlertsPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "HOSPITAL") as PortalRole);

  const alerts = useQuery({
    queryKey: ["alerts", 100],
    queryFn: () => fetchAlerts(100),
    refetchInterval: LIVE_REFRESH,
  });

  const rows = alerts.data ?? [];

  return (
    <div className="page-body">
      <PageHeader
        title="Alerts"
        subtitle={item?.subtitle ?? "Fleet emergency, timeout and device-offline alerts"}
      />

      {alerts.error && <InlineError error={alerts.error} fallback="Could not load alerts." />}

      {alerts.isLoading ? (
        <Loading label="Loading alerts" />
      ) : rows.length === 0 ? (
        <Empty
          icon="notifications_active"
          title="No alerts"
          body="Timeouts, device-offline events and emergency alerts for your fleet appear here."
        />
      ) : (
        rows.map((alert, i) => (
          <Card
            key={`${alert.at}-${i}`}
            style={{ display: "flex", flexDirection: "column", gap: 8 }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 10,
                flexWrap: "wrap",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <Badge label={alert.severity} tone={severityTone(alert.severity)} />
                <Txt muted style={{ fontSize: 12 }}>
                  {alert.type.replaceAll("_", " ")}
                </Txt>
              </div>
              <Txt muted>{fmtDateTime(alert.at)}</Txt>
            </div>
            <Txt>{alert.message}</Txt>
          </Card>
        ))
      )}
    </div>
  );
}
