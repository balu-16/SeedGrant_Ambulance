/**
 * ADMIN Emergencies (plan §4.1) — full history table across all drivers and
 * hospitals with server-side filters (status, date range, ambulance, junction,
 * hospital — contract §3), limit/offset pagination, the server CSV export
 * (exportEmergenciesCsv — Authorization header + blob download) and a detail
 * drawer rendering GET /emergencies/{id}/timeline.
 *
 * A failed refetch never wipes the table: keepPreviousData retains the last
 * successful rows and the error renders as a banner above them.
 */

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  exportEmergenciesCsv,
  fetchEmergencies,
  fetchEmergencyTimeline,
  listAmbulances,
  listHospitals,
  listJunctions,
  type EmergencyFilters,
} from "@/services/portal";
import type { EmergencyRow, TimelineEvent } from "@/types/portal";
import { statusTone } from "@/components/helpers";
import {
  Badge,
  Card,
  Drawer,
  Empty,
  PageHeader,
  SectionTitle,
  Table,
  Timeline,
  Txt,
  type TableColumn,
} from "@/components/ui";
import {
  fmtDateTime,
  fmtDuration,
  timelineTone,
} from "@/pages/admin/shared";
import {
  ErrorCard,
  KVList,
  LoadingBlock,
  MiniButton,
  SelectField,
} from "@/pages/admin/widgets";
import "@/pages/admin/admin.css";

const STATUSES = ["ALL", "COMPLETED", "ACTIVE", "CANCELLED", "TIMED_OUT"];
const LIMIT = 15;

export function EmergenciesPage() {
  const [status, setStatus] = useState("ALL");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [ambulanceId, setAmbulanceId] = useState("");
  const [junctionId, setJunctionId] = useState("");
  const [hospitalId, setHospitalId] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<EmergencyRow | null>(null);

  const ambulances = useQuery({
    queryKey: ["admin", "ambulances"],
    queryFn: listAmbulances,
  });
  const junctions = useQuery({
    queryKey: ["admin", "junctions"],
    queryFn: listJunctions,
  });
  const hospitals = useQuery({
    queryKey: ["admin", "hospitals"],
    queryFn: listHospitals,
  });

  const filters: EmergencyFilters = useMemo(
    () => ({
      status: status === "ALL" ? undefined : status,
      from: from || undefined,
      to: to || undefined,
      ambulance_id: ambulanceId || undefined,
      junction_id: junctionId || undefined,
      hospital_id: hospitalId || undefined,
    }),
    [status, from, to, ambulanceId, junctionId, hospitalId],
  );
  const filterCount = Object.values(filters).filter((v) => v !== undefined).length;

  const q = useQuery({
    queryKey: ["admin", "emergencies", filters, offset],
    queryFn: () => fetchEmergencies({ ...filters, limit: LIMIT, offset }),
    placeholderData: keepPreviousData,
  });

  const exportM = useMutation({
    mutationFn: () => exportEmergenciesCsv(filters),
  });

  const items = q.data?.items ?? [];

  const onRowSelect = (row: (typeof items)[number]) => setSelected(row);

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
      key: "hospital",
      header: "Hospital",
      render: (r) => r.owner_hospital_name ?? "—",
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

      {/* Failed refetch keeps the previous table (keepPreviousData) and
          renders as a banner — never an empty/zero state. */}
      {q.isError && (
        <ErrorCard
          title="Could not refresh emergencies — showing the last loaded rows"
          error={q.error}
          onRetry={() => void q.refetch()}
        />
      )}
      {exportM.isError && (
        <ErrorCard
          title="CSV export failed"
          error={exportM.error}
          onRetry={() => exportM.reset()}
        />
      )}

      {q.isPending && !q.data ? (
        <LoadingBlock label="Loading emergencies" />
      ) : (
        <>
          <div className="admin-toolbar">
            <SelectField
              label="Status"
              value={status}
              onChange={(v) => {
                setStatus(v);
                setOffset(0);
              }}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </SelectField>
            <div className="field" style={{ minHeight: 46, minWidth: 170 }}>
              <div className="field-body">
                <label className="field-label" htmlFor="emg-from-filter">
                  From date
                </label>
                <input
                  id="emg-from-filter"
                  className="admin-select"
                  type="date"
                  value={from}
                  max={to || undefined}
                  onChange={(e) => {
                    setFrom(e.target.value);
                    setOffset(0);
                  }}
                />
              </div>
            </div>
            <div className="field" style={{ minHeight: 46, minWidth: 170 }}>
              <div className="field-body">
                <label className="field-label" htmlFor="emg-to-filter">
                  To date
                </label>
                <input
                  id="emg-to-filter"
                  className="admin-select"
                  type="date"
                  value={to}
                  min={from || undefined}
                  onChange={(e) => {
                    setTo(e.target.value);
                    setOffset(0);
                  }}
                />
              </div>
            </div>
            <SelectField
              label="Ambulance"
              value={ambulanceId}
              onChange={(v) => {
                setAmbulanceId(v);
                setOffset(0);
              }}
            >
              <option value="">All ambulances</option>
              {(ambulances.data ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.vehicle_no}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Junction"
              value={junctionId}
              onChange={(v) => {
                setJunctionId(v);
                setOffset(0);
              }}
            >
              <option value="">All junctions</option>
              {(junctions.data ?? []).map((j) => (
                <option key={j.id} value={j.id}>
                  {j.name}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Hospital"
              value={hospitalId}
              onChange={(v) => {
                setHospitalId(v);
                setOffset(0);
              }}
            >
              <option value="">All hospitals</option>
              {(hospitals.data ?? []).map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}
                </option>
              ))}
            </SelectField>
            {filterCount > 0 && (
              <MiniButton
                title="Clear filters"
                onClick={() => {
                  setStatus("ALL");
                  setFrom("");
                  setTo("");
                  setAmbulanceId("");
                  setJunctionId("");
                  setHospitalId("");
                  setOffset(0);
                }}
              />
            )}
            <Txt muted style={{ marginLeft: "auto" }}>
              {q.data?.total != null
                ? `${offset + 1}–${offset + items.length} of ${q.data.total}`
                : `offset ${offset} · ${items.length} rows`}
            </Txt>
            <MiniButton
              title="Export CSV"
              icon="download"
              loading={exportM.isPending}
              onClick={() => exportM.mutate()}
            />
            <MiniButton
              title="Prev"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - LIMIT))}
            />
            <MiniButton
              title="Next"
              disabled={
                q.data?.total != null
                  ? offset + LIMIT >= q.data.total
                  : items.length < LIMIT
              }
              onClick={() => setOffset(offset + LIMIT)}
            />
          </div>

          <div>
            <Table
              columns={columns}
              rows={items}
              keyOf={(r) => r.id}
              onRowClick={onRowSelect}
              emptyFallback={
                filterCount > 0 ? (
                  <Empty
                    icon="emergency"
                    title="No emergencies match these filters"
                    body="Try widening the date range or clearing a filter — the server applies them to the full authorized history."
                  />
                ) : (
                  <Empty
                    icon="emergency"
                    title="No emergencies found"
                    body="Emergency history appears here once drivers start sessions."
                  />
                )
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
        {selected && <EmergencyDetail key={selected.id} row={selected} />}
      </Drawer>
    </div>
  );
}

/** Detail drawer body: identity + the session timeline (contract §4). */
function EmergencyDetail({ row }: { row: EmergencyRow }) {
  const timeline = useQuery({
    queryKey: ["admin", "timeline", row.id],
    queryFn: () => fetchEmergencyTimeline(row.id),
  });

  const events: TimelineEvent[] = useMemo(() => {
    const raw = timeline.data?.items ?? [];
    return [...raw].sort((a, b) => {
      const ta = a.at ? new Date(a.at).getTime() : Number.POSITIVE_INFINITY;
      const tb = b.at ? new Date(b.at).getTime() : Number.POSITIVE_INFINITY;
      return ta - tb;
    });
  }, [timeline.data]);

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Badge label={row.status} tone={statusTone(row.status)} />
      </div>
      <Card>
        <KVList
          entries={[
            ["Emergency", row.id],
            ["Driver", row.driver_email ?? "—"],
            ["Ambulance", row.ambulance_vehicle_no ?? "—"],
            ["Hospital", row.owner_hospital_name ?? "—"],
            ["Started", fmtDateTime(row.started_at)],
            ["Ended", fmtDateTime(row.ended_at)],
            ["End reason", row.ended_reason ?? "—"],
            [
              "Duration",
              fmtDuration(row.started_at, row.ended_at) ??
                (row.started_at ? "ongoing" : "—"),
            ],
          ]}
        />
      </Card>

      <SectionTitle>Timeline</SectionTitle>
      {timeline.isError ? (
        <ErrorCard
          title="Could not load the timeline"
          error={timeline.error}
          onRetry={() => void timeline.refetch()}
        />
      ) : timeline.isPending ? (
        <LoadingBlock label="Loading timeline" />
      ) : events.length === 0 ? (
        <Txt muted>No timeline events recorded for this emergency yet.</Txt>
      ) : (
        <Timeline
          items={events.map((e) => ({
            title:
              e.kind === "command"
                ? `${e.type}${e.approach ? ` · ${e.approach}` : ""}`
                : e.type,
            meta:
              e.kind === "command"
                ? `${e.status ?? "—"} · ${fmtDateTime(e.at)}`
                : `audit · ${fmtDateTime(e.at)}`,
            tone: e.status ? timelineTone(e.status) : "neutral",
          }))}
        />
      )}
      <Txt muted>
        A command acknowledgement means the junction device received the request
        — it is not a confirmation that the signal changed.
      </Txt>
    </>
  );
}
