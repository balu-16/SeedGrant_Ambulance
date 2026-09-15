/**
 * ADMIN Devices (plan §4.1) — Pi device health table (junction lookup, online
 * badge, last heartbeat) polled every 10s; the detail drawer streams the
 * junction's telemetry (latest first, monospace JSON).
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { listDevices, listJunctions, listTelemetry, registerDevice, rotateDeviceKey } from "@/services/portal";
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
  const queryClient = useQueryClient();
  const [regJunctionId, setRegJunctionId] = useState("");
  const [regName, setRegName] = useState("");
  const [regResult, setRegResult] = useState<string | null>(null);
  const [regError, setRegError] = useState<string | null>(null);

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
        <div>
          <Card>
            <Txt style={{ fontWeight: 700 }}>Register Pi device</Txt>
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              <select value={regJunctionId} onChange={(e) => setRegJunctionId(e.target.value)}>
                <option value="">Select junction…</option>
                {(junctions.data ?? []).map((j) => (
                  <option key={j.id} value={j.id}>{j.name}</option>
                ))}
              </select>
              <input
                placeholder="Device name"
                value={regName}
                onChange={(e) => setRegName(e.target.value)}
              />
              <button
                onClick={() => {
                  setRegError(null);
                  setRegResult(null);
                  if (!regJunctionId || !regName.trim()) {
                    setRegError("Pick a junction and enter a device name.");
                    return;
                  }
                  void registerDevice(regJunctionId, regName.trim())
                    .then((r) => {
                      setRegResult(`API key (shown once): ${r.api_key}`);
                      setRegName("");
                      void queryClient.invalidateQueries({ queryKey: ["admin", "devices"] });
                    })
                    .catch((e: unknown) => setRegError(e instanceof Error ? e.message : "Register failed"));
                }}
              >
                Register
              </button>
            </div>
            {regError ? <Txt style={{ color: "var(--red)" }}>{regError}</Txt> : null}
            {regResult ? <Txt style={{ color: "var(--green)" }}>{regResult}</Txt> : null}
          </Card>
          <div style={{ height: 12 }} />
          <Table
            columns={[
              ...columns,
              {
                key: "actions",
                header: "Key",
                render: (d) => (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!confirm(`Rotate API key for device ${d.id.slice(0, 8)}? Old key stops working.`)) return;
                      setRegError(null);
                      setRegResult(null);
                      void rotateDeviceKey(d.id)
                        .then((r) => setRegResult(`API key (shown once): ${r.api_key}`))
                        .catch((err: unknown) => setRegError(err instanceof Error ? err.message : "Rotate failed"));
                    }}
                  >
                    Rotate key
                  </button>
                ),
              },
            ]}
            rows={items}
            keyOf={(d) => d.id}
            onRowClick={(d) => setSelectedId(d.id)}
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
