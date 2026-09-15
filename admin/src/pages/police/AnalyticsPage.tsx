/**
 * POLICE Analytics (plan §4.3) — scoped aggregates over a selectable window
 * (1/7/30/90 days): headline StatCards plus pure-CSS bar charts for command
 * outcomes (by status) and emergencies per junction. No chart library.
 */

import { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { Card, Empty, PageHeader, SectionTitle, StatCard, Txt } from "@/components/ui";
import { fetchAnalytics, listJunctions } from "@/services/portal";
import { Loading, InlineError, SelectField } from "@/pages/shared/bits";
import { statusBadgeTone, toneColor } from "@/pages/shared/format";

const DAY_OPTIONS = [
  { value: "1", label: "Last 24 hours" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

interface BarEntry {
  label: string;
  value: number;
  color: string;
}

/** Pure-CSS horizontal bar list (label — bar — value), like the app stats. */
function BarList({ entries, unit }: { entries: BarEntry[]; unit?: string }) {
  const max = Math.max(...entries.map((e) => e.value), 1);
  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {entries.map((entry) => (
        <div
          key={entry.label}
          style={{ display: "flex", alignItems: "center", gap: 10 }}
        >
          <Txt
            style={{ width: 130, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {entry.label}
          </Txt>
          <div
            style={{
              flex: 1,
              height: 12,
              borderRadius: 6,
              background: "var(--pale)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${Math.max((entry.value / max) * 100, entry.value > 0 ? 4 : 0)}%`,
                height: "100%",
                borderRadius: 6,
                background: entry.color,
              }}
            />
          </div>
          <Txt style={{ width: 44, textAlign: "right", flexShrink: 0, fontWeight: 600 }}>
            {entry.value}
            {unit ?? ""}
          </Txt>
        </div>
      ))}
    </Card>
  );
}

export function PoliceAnalyticsPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "police") as PortalRole);

  const [days, setDays] = useState("7");

  const junctionIds = useMemo(() => user?.junction_ids ?? [], [user]);
  const junctions = useQuery({ queryKey: ["junctions"], queryFn: listJunctions });
  const nameByJunction = new Map(
    (junctions.data ?? []).map((j) => [j.id, j.name]),
  );

  const analytics = useQuery({
    queryKey: ["analytics", days],
    queryFn: () => fetchAnalytics(Number(days)),
  });

  const overview = analytics.data;
  const commandBars: BarEntry[] = overview
    ? Object.entries(overview.commands.by_status).map(([status, count]) => ({
        label: status,
        value: count,
        color: toneColor(statusBadgeTone(status)),
      }))
    : [];
  const junctionBars: BarEntry[] = overview
    ? overview.junctions
        .filter((row) => junctionIds.length === 0 || junctionIds.includes(row.junction_id))
        .map((row) => ({
          label: nameByJunction.get(row.junction_id) ?? row.junction_id,
          value: row.emergencies,
          color: "var(--blue)",
        }))
    : [];

  return (
    <div className="page-body">
      <PageHeader
        title="Analytics"
        subtitle={item?.subtitle ?? "Crossing times, command outcomes and peak hours"}
      />

      <div style={{ maxWidth: 320 }}>
        <SelectField
          label="Period"
          value={days}
          onChange={setDays}
          options={DAY_OPTIONS}
        />
      </div>

      {analytics.error && (
        <InlineError error={analytics.error} fallback="Could not load analytics." />
      )}

      {analytics.isLoading || !overview ? (
        <Loading label="Loading analytics" />
      ) : (
        <>
          <div className="stat-grid">
            <StatCard
              label="Emergencies"
              value={String(overview.emergencies.total)}
              tone="red"
              icon="emergency"
            />
            <StatCard
              label="Avg Duration"
              value={
                overview.emergencies.avg_duration_minutes === null
                  ? "—"
                  : `${Math.round(overview.emergencies.avg_duration_minutes)} min`
              }
              tone="purple"
              icon="timer"
            />
            <StatCard
              label="Commands"
              value={String(overview.commands.total)}
              tone="blue"
              icon="terminal"
            />
            <StatCard
              label="Devices Online"
              value={`${overview.devices.online} / ${overview.devices.total}`}
              tone="green"
              icon="memory"
            />
          </div>

          <SectionTitle>Commands by Status</SectionTitle>
          {commandBars.length === 0 ? (
            <Empty
              icon="terminal"
              title="No commands in this period"
              body="Command outcomes for your junctions appear here once priority commands are issued."
            />
          ) : (
            <BarList entries={commandBars} />
          )}

          <SectionTitle>Emergencies per Junction</SectionTitle>
          {junctionBars.length === 0 ? (
            <Empty
              icon="traffic"
              title="No junction activity in this period"
              body="Emergency counts per assigned junction appear here once your fleet serves calls."
            />
          ) : (
            <BarList entries={junctionBars} />
          )}
        </>
      )}
    </div>
  );
}
