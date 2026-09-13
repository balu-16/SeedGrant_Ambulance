/**
 * ADMIN Devices (plan §4.1) — Pi device health table (junction lookup, online
 * badge, last heartbeat) polled every 10s; the detail drawer streams the
 * junction's telemetry (latest first, monospace JSON).
 */

import { useQuery } from "@tanstack/react-query";
import { useState, type MouseEvent } from "react";
import { listDevices, listJunctions, listTelemetry } from "@/services/portal";
import type { DeviceStatus } from "@/types/portal";
import { Badge, Card, Drawer, Empty, PageHeader, Table, Txt, type TableColumn } from "@/components/ui";
import { fmtAgo, fmtDateTime, shortId } from "@/pages/admin/shared";
import {
  ErrorCard,
  LoadingBlock,
} from "@/pages/admin/widgets";
import "@/pages/admin/admin.css";

export function DevicesPage() {
  const devices = useQuery({
    queryKey: ["admin", "devices"],
    queryFn: listDevices,
    refetchInterval: 10_000,
  });
  const junctions = useQuery({
    queryKey: ["admin", "junctions"],
    queryFn: listJunctions,
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const items = devices.data ?? [];
  const junctionNames = new Map(
    (junctions.data ?? []).map((j) => [j.id, j.name]),
  );
  const selected = items.find((d) => d.id === selectedId) ?? null;

  const onRowClick = (e: MouseEvent<HTMLDivElement>) => {
    const tr = (e.target as HTMLElement).closest("tr");
    if (!tr || tr.rowIndex === 0) return;
    const row = items[tr.rowIndex - 1];
    if (row) setSelectedId(row.id);
  };

  const columns: TableColumn<DeviceStatus>[] = [
    {
      key: "id",
      header: "Device",
      render: (d) => (
        <span className="admin-mono" title={d.id} style={{ color: "var(--navy)" }}>
          {shortId(d.id)}
        </span>
      ),
    },
    {
      key: "junction",
      header: "Junction",
      render: (d) =>
        junctionNames.get(d.junction_id) ?? shortId(d.junction_id),
    },
    {
      key: "online",
      header: "Online",
      render: (d) => (
        <Badge label={d.online ? "ONLINE" : "OFFLINE"} tone={d.online ? "green" : "red"} />
      ),
    },
    {
      key: "last_seen",
      header: "Last seen",
      render: (d) => (
        <Txt muted>
          {d.last_seen ? `${fmtAgo(d.last_seen)} · ${fmtDateTime(d.last_seen)}` : "never"}
        </Txt>
      ),
    },
  ];

  return (
    <div className="page-body">
      <PageHeader
        title="Devices"
        subtitle="Registered Pi devices, keys and heartbeats"
      />

      {devices.isError ? (
        <ErrorCard
          title="Could not load devices"
          error={devices.error}
          onRetry={() => void devices.refetch()}
        />
      ) : devices.isLoading ? (
        <LoadingBlock label="Loading devices" />
      ) : (
        <div className="admin-row-click" onClick={onRowClick}>
          <Table
            columns={columns}
            rows={items}
            keyOf={(d) => d.id}
            emptyFallback={
              <Empty
                icon="memory"
                title="No devices registered"
                body="Pi controllers register themselves with the backend on first boot."
              />
            }
          />
        </div>
      )}

      <Drawer
        open={selected !== null}
        title="Device telemetry"
        onClose={() => setSelectedId(null)}
        width={500}
      >
        {selected && (
          <TelemetryList
            junctionId={selected.junction_id}
            junctionLabel={
              junctionNames.get(selected.junction_id) ?? selected.junction_id
            }
          />
        )}
      </Drawer>
    </div>
  );
}

function TelemetryList({
  junctionId,
  junctionLabel,
}: {
  junctionId: string;
  junctionLabel: string;
}) {
  const q = useQuery({
    queryKey: ["admin", "telemetry", junctionId],
    queryFn: () => listTelemetry(junctionId),
    refetchInterval: 10_000,
  });

  const rows = [...(q.data?.items ?? [])].sort(
    (a, b) => new Date(b.at).getTime() - new Date(a.at).getTime(),
  );

  return (
    <>
      <Txt muted>
        Latest readings from <b>{junctionLabel}</b>, newest first.
      </Txt>
      {q.isError ? (
        <ErrorCard
          title="Could not load telemetry"
          error={q.error}
          onRetry={() => void q.refetch()}
        />
      ) : q.isLoading ? (
        <LoadingBlock label="Loading telemetry" />
      ) : rows.length === 0 ? (
        <Empty
          icon="sensors"
          title="No telemetry yet"
          body="The device has not reported any sensor readings for this junction."
        />
      ) : (
        <div className="admin-scroll">
          {rows.map((r, i) => (
            <Card key={`${r.at}-${i}`} style={{ padding: 12 }}>
              <Txt muted className="admin-mono">
                {fmtDateTime(r.at)}
              </Txt>
              <pre
                className="admin-mono"
                style={{
                  margin: "6px 0 0",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  color: "var(--heading)",
                }}
              >
                {JSON.stringify(r.payload, null, 2)}
              </pre>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
