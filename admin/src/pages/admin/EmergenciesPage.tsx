/**
 * ADMIN Emergencies (plan §4.1) — full history table across all drivers and
 * hospitals with a server-side status filter, limit/offset pagination and a
 * detail drawer for every row.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState, type MouseEvent } from "react";
import { fetchEmergencies } from "@/services/portal";
import type { EmergencyRow } from "@/types/portal";
import { statusTone } from "@/components/helpers";
import {
  Badge,
  Card,
  Drawer,
  Empty,
  PageHeader,
  Table,
  Txt,
  type TableColumn,
} from "@/components/ui";
import { fmtDateTime, fmtDuration } from "@/pages/admin/shared";
import {
  ErrorCard,
  KVList,
  LoadingBlock,
  MiniButton,
} from "@/pages/admin/widgets";
import "@/pages/admin/admin.css";

const STATUSES = ["ALL", "COMPLETED", "ACTIVE", "CANCELLED", "TIMED_OUT"];
const LIMIT = 15;

export function EmergenciesPage() {
  const [status, setStatus] = useState("ALL");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<EmergencyRow | null>(null);

  const q = useQuery({
    queryKey: ["admin", "emergencies", status, offset],
    queryFn: () =>
      fetchEmergencies({
        limit: LIMIT,
        offset,
        status: status === "ALL" ? undefined : status,
      }),
    placeholderData: keepPreviousData,
  });

  const items = q.data?.items ?? [];

  /** Row-click delegation — the shared Table renders plain <tr> elements. */
  const onRowClick = (e: MouseEvent<HTMLDivElement>) => {
    const tr = (e.target as HTMLElement).closest("tr");
    if (!tr || tr.rowIndex === 0) return; // header row
    const row = items[tr.rowIndex - 1];
    if (row) setSelected(row);
  };

  const columns: TableColumn<EmergencyRow>[] = [
    {
      key: "started_at",
      header: "Started",
      render: (r) => fmtDateTime(r.started_at),
    },
    {
      key: "status",
      header: "Status",
      render: (r) => <Badge label={r.status} tone={statusTone(r.status)} />,
    },
    {
      key: "driver_email",
      header: "Driver",
      render: (r) => r.driver_email ?? "—",
    },
    {
      key: "ambulance_vehicle_no",
      header: "Ambulance",
      render: (r) => r.ambulance_vehicle_no ?? "—",
    },
    {
      key: "duration",
      header: "Duration",
      render: (r) =>
        fmtDuration(r.started_at, r.ended_at) ??
        (r.started_at ? "ongoing" : "—"),
    },
  ];

  return (
    <div className="page-body">
      <PageHeader
        title="Emergencies"
        subtitle="Emergency history with event timelines and exports"
      />

      {q.isError ? (
        <ErrorCard
          title="Could not load emergencies"
          error={q.error}
          onRetry={() => void q.refetch()}
        />
      ) : q.isLoading ? (
        <LoadingBlock label="Loading emergencies" />
      ) : (
        <>
          <div className="admin-toolbar">
            <div className="field" style={{ minHeight: 46, minWidth: 200 }}>
              <div className="field-body">
                <label className="field-label" htmlFor="emg-status-filter">
                  Status
                </label>
                <select
                  id="emg-status-filter"
                  className="admin-select"
                  value={status}
                  onChange={(e) => {
                    setStatus(e.target.value);
                    setOffset(0);
                  }}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <Txt muted style={{ marginLeft: "auto" }}>
              offset {offset} · {items.length} rows
            </Txt>
            <MiniButton
              title="Prev"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - LIMIT))}
            />
            <MiniButton
              title="Next"
              disabled={items.length < LIMIT}
              onClick={() => setOffset(offset + LIMIT)}
            />
          </div>

          <div className="admin-row-click" onClick={onRowClick}>
            <Table
              columns={columns}
              rows={items}
              keyOf={(r) => r.id}
              emptyFallback={
                <Empty
                  icon="emergency"
                  title="No emergencies found"
                  body={
                    status === "ALL"
                      ? "Emergency history appears here once drivers start sessions."
                      : `No ${status} emergencies on this page — try another status.`
                  }
                />
              }
            />
          </div>
        </>
      )}

      <Drawer
        open={selected !== null}
        title="Emergency detail"
        onClose={() => setSelected(null)}
        width={440}
      >
        {selected && (
          <>
            <Badge label={selected.status} tone={statusTone(selected.status)} />
            <Card>
              <KVList
                entries={[
                  ["Emergency", selected.id],
                  ["Driver", selected.driver_email ?? "—"],
                  ["Ambulance", selected.ambulance_vehicle_no ?? "—"],
                  ["Started", fmtDateTime(selected.started_at)],
                  ["Ended", fmtDateTime(selected.ended_at)],
                  ["End reason", selected.ended_reason ?? "—"],
                  [
                    "Duration",
                    fmtDuration(selected.started_at, selected.ended_at) ??
                      (selected.started_at ? "ongoing" : "—"),
                  ],
                ]}
              />
            </Card>
            <Txt muted>
              Live positions and command timelines for active sessions are on
              the Live Map page.
            </Txt>
          </>
        )}
      </Drawer>
    </div>
  );
}
