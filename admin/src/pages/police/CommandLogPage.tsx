/**
 * POLICE Command Log (plan §4.3) — every command for the officer's junctions
 * with junction/status filters and result limit; correlation ids render
 * truncated in monospace with the full id on hover. Polls every 10s so
 * PENDING → SENT → ACKNOWLEDGED transitions appear live.
 */

import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { useLocation } from "react-router-dom";
import { Badge, Empty, PageHeader, Table, Txt } from "@/components/ui";
import { listCommands, listJunctions } from "@/services/portal";
import { Loading, InlineError, SelectField } from "@/pages/shared/bits";
import { fmtDateTime, statusBadgeTone } from "@/pages/shared/format";

const LIVE_REFRESH = 10_000;

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "PENDING", label: "Pending" },
  { value: "SENT", label: "Sent" },
  { value: "ACKNOWLEDGED", label: "Acknowledged" },
  { value: "RELEASED", label: "Released" },
  { value: "EXPIRED", label: "Expired" },
  { value: "FAILED", label: "Failed" },
  { value: "CANCELLED", label: "Cancelled" },
];

const LIMIT_OPTIONS = [
  { value: "25", label: "25 results" },
  { value: "50", label: "50 results" },
  { value: "100", label: "100 results" },
  { value: "200", label: "200 results" },
];

function Correlation({ value }: { value: string }) {
  const short = value.length > 10 ? `${value.slice(0, 10)}…` : value;
  return (
    <code
      title={value}
      style={{
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        fontSize: 12,
      }}
    >
      {short}
    </code>
  );
}

export function PoliceCommandLogPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "police") as PortalRole);

  const junctionIds = useMemo(() => user?.junction_ids ?? [], [user]);
  const junctions = useQuery({ queryKey: ["junctions"], queryFn: listJunctions });
  const mine = (junctions.data ?? []).filter((j) => junctionIds.includes(j.id));
  const nameByJunction = new Map(mine.map((j) => [j.id, j.name]));

  const [junctionId, setJunctionId] = useState("");
  const [status, setStatus] = useState("");
  const [limit, setLimit] = useState("50");

  const commands = useQuery({
    queryKey: ["commands", junctionId, status, limit],
    queryFn: () =>
      listCommands({
        junction_id: junctionId || undefined,
        status: status || undefined,
        limit: Number(limit),
      }),
    placeholderData: keepPreviousData,
    refetchInterval: LIVE_REFRESH,
  });

  const rows = commands.data ?? [];

  return (
    <div className="page-body">
      <PageHeader
        title="Command Log"
        subtitle={item?.subtitle ?? "Commands for your junctions with status and retries"}
      />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 10,
        }}
      >
        <SelectField
          label="Junction"
          value={junctionId}
          onChange={setJunctionId}
          options={[
            { value: "", label: "All my junctions" },
            ...mine.map((j) => ({ value: j.id, label: j.name })),
          ]}
        />
        <SelectField
          label="Status"
          value={status}
          onChange={setStatus}
          options={STATUS_OPTIONS}
        />
        <SelectField
          label="Limit"
          value={limit}
          onChange={setLimit}
          options={LIMIT_OPTIONS}
        />
      </div>

      {commands.error && (
        <InlineError error={commands.error} fallback="Could not load the command log." />
      )}

      {commands.isLoading ? (
        <Loading label="Loading commands" />
      ) : rows.length === 0 ? (
        <Empty
          icon="terminal"
          title="No commands found"
          body="Priority commands issued to your junctions (with retries and acknowledgement state) appear here."
        />
      ) : (
        <Table
          rows={rows}
          keyOf={(row) => row.id}
          columns={[
            {
              key: "created_at",
              header: "Created",
              render: (row) => fmtDateTime(row.created_at),
            },
            { key: "type", header: "Type", render: (row) => <Txt style={{ fontWeight: 600 }}>{row.type}</Txt> },
            {
              key: "status",
              header: "Status",
              render: (row) => (
                <Badge label={row.status} tone={statusBadgeTone(row.status)} />
              ),
            },
            { key: "approach", header: "Approach", render: (row) => row.approach || "—" },
            {
              key: "junction",
              header: "Junction",
              render: (row) => nameByJunction.get(row.junction_id) ?? row.junction_id,
            },
            { key: "retry_count", header: "Retries", align: "right" },
            {
              key: "expires_at",
              header: "Expires",
              render: (row) => fmtDateTime(row.expires_at),
            },
            {
              key: "ack_at",
              header: "Acked",
              render: (row) => fmtDateTime(row.ack_at),
            },
            {
              key: "correlation_id",
              header: "Correlation",
              render: (row) => <Correlation value={row.correlation_id} />,
            },
          ]}
        />
      )}
    </div>
  );
}
