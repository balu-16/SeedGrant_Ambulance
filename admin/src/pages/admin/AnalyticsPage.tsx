/**
 * ADMIN Analytics (plan §4.1) — date-range selector (1/7/30/90 days) feeding
 * fetchAnalytics; StatCards for totals plus CSS-only bar charts (no chart
 * library) for emergencies and commands by status and per-junction load.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchAnalytics, listJunctions } from "@/services/portal";
import { statusTone } from "@/components/helpers";
import { PageHeader, Row, StatCard, Card, Txt } from "@/components/ui";
import { shortId } from "@/pages/admin/shared";
import { BarList, ErrorCard, LoadingBlock, MiniButton } from "@/pages/admin/widgets";
import "@/pages/admin/admin.css";

const DAY_OPTIONS = [1, 7, 30, 90];

export function AnalyticsPage() {
  const [days, setDays] = useState(7);
  const analytics = useQuery({
    queryKey: ["admin", "analytics", days],
    queryFn: () => fetchAnalytics(days),
  });
  const junctions = useQuery({
    queryKey: ["admin", "junctions"],
    queryFn: listJunctions,
  });

  const data = analytics.data;
  const junctionNames = new Map(
    (junctions.data ?? []).map((j) => [j.id, j.name]),
  );

  return (
    <div className="page-body">
      <PageHeader
        title="Analytics"
        subtitle="Crossing times, command outcomes and peak hours"
      >
        <Row>
          {DAY_OPTIONS.map((d) => (
            <MiniButton
              key={d}
              title={d === 1 ? "1 day" : `${d} days`}
              tone={days === d ? "primary" : "quiet"}
              onClick={() => setDays(d)}
            />
          ))}
        </Row>
      </PageHeader>

      {analytics.isError ? (
        <ErrorCard
          title="Could not load analytics"
          error={analytics.error}
          onRetry={() => void analytics.refetch()}
        />
      ) : analytics.isLoading ? (
        <LoadingBlock label="Loading analytics" />
      ) : data ? (
        <>
          <div className="stat-grid">
            <StatCard
              label="Total Emergencies"
              value={String(data.emergencies.total)}
              tone="red"
              icon="emergency"
            />
            <StatCard
              label="Avg Duration"
              value={
                data.emergencies.avg_duration_minutes != null
                  ? `${Math.round(data.emergencies.avg_duration_minutes)} min`
                  : "—"
              }
              tone="blue"
              icon="timer"
            />
            <StatCard
              label="Commands"
              value={String(data.commands.total)}
              tone="purple"
              icon="terminal"
            />
            <StatCard
              label="Devices Online"
              value={`${data.devices.online} / ${data.devices.total}`}
              tone="green"
              icon="memory"
            />
          </div>

          <div className="admin-cards">
            <Card>
              <Txt as="div" style={{ fontWeight: 600, marginBottom: 10 }}>
                Emergencies by status
              </Txt>
              <BarList
                rows={Object.entries(data.emergencies.by_status).map(
                  ([label, value]) => ({
                    label,
                    value,
                    tone: statusTone(label),
                  }),
                )}
              />
            </Card>

            <Card>
              <Txt as="div" style={{ fontWeight: 600, marginBottom: 10 }}>
                Commands by status
              </Txt>
              <BarList
                rows={Object.entries(data.commands.by_status).map(
                  ([label, value]) => ({
                    label,
                    value,
                    tone: statusTone(label),
                  }),
                )}
              />
            </Card>

            <Card style={{ gridColumn: "1 / -1" }}>
              <Txt as="div" style={{ fontWeight: 600, marginBottom: 10 }}>
                Emergencies per junction
              </Txt>
              <BarList
                rows={data.junctions.map((j) => ({
                  label: junctionNames.get(j.junction_id) ?? shortId(j.junction_id),
                  value: j.emergencies,
                  tone: "blue" as const,
                }))}
                emptyText="No junction activity in this range."
              />
            </Card>
          </div>
        </>
      ) : null}
    </div>
  );
}
