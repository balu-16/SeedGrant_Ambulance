/**
 * HOSPITAL Emergencies (plan §4.2) — server-scoped history with the same
 * server-side filters as admin minus hospital (status, date range, ambulance,
 * junction — contract §3), offset pagination, the server CSV export
 * (exportEmergenciesCsv — Authorization header + blob download, same filter
 * set) and a detail drawer with the session timeline (GET
 * /emergencies/{id}/timeline). A failed refetch keeps the previous rows.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { useLocation } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  Drawer,
  Empty,
  PageHeader,
  SectionTitle,
  Table,
  Timeline,
  Txt,
} from "@/components/ui";
import {
  exportEmergenciesCsv,
  fetchEmergencies,
  fetchEmergencyTimeline,
  listAmbulances,
  listJunctions,
  type EmergencyFilters,
} from "@/services/portal";
import type { EmergencyRow, TimelineEvent } from "@/types/portal";
import {
  FreshnessCaption,
  InlineError,
  Loading,
  SelectField,
  StaleBanner,
} from "@/pages/shared/bits";
import {
  durationMinutes,
  fmtDateTime,
  statusBadgeTone,
  timelineTone,
} from "@/pages/shared/format";
import { isStale, useFreshnessThresholds } from "@/pages/shared/freshness";
import { ApiError } from "@/services/api";
// Toolbar/field layout classes shared with the admin emergencies page.
import "@/pages/admin/admin.css";

const PAGE_SIZE = 25;

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "ACTIVE", label: "Active (all in-flight)" },
  { value: "COMPLETED", label: "Completed" },
  { value: "CANCELLED", label: "Cancelled" },
  { value: "TIMED_OUT", label: "Timed out" },
];

export function HospitalEmergenciesPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "hospital") as PortalRole);
  const thresholds = useFreshnessThresholds();

  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [ambulanceId, setAmbulanceId] = useState("");
  const [junctionId, setJunctionId] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<EmergencyRow | null>(null);
  const [exportErr, setExportErr] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const ambulances = useQuery({ queryKey: ["ambulances"], queryFn: listAmbulances });
  const junctions = useQuery({ queryKey: ["junctions"], queryFn: listJunctions });

  const filters: EmergencyFilters = useMemo(
    () => ({
      status: status || undefined,
      from: from || undefined,
      to: to || undefined,
      ambulance_id: ambulanceId || undefined,
      junction_id: junctionId || undefined,
    }),
    [status, from, to, ambulanceId, junctionId],
  );
  const filterCount = Object.values(filters).filter((v) => v !== undefined).length;

  const emergencies = useQuery({
    queryKey: ["emergencies", filters, offset],
    queryFn: () => fetchEmergencies({ ...filters, limit: PAGE_SIZE, offset }),
    placeholderData: keepPreviousData,
  });

  const rows = emergencies.data?.items ?? [];
  const total = emergencies.data?.total;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const canPrev = offset > 0;
  const canNext = total != null ? offset + PAGE_SIZE < total : rows.length === PAGE_SIZE;
  const stale =
    emergencies.data !== undefined &&
    isStale(emergencies.dataUpdatedAt, thresholds.portalStaleSeconds);

  const changeStatus = (value: string) => {
    setStatus(value);
    setOffset(0);
  };

  const exportCsv = async () => {
    setExportErr(null);
    setExporting(true);
    try {
      // Server-side export: all authorized rows matching the filters (contract §3).
      await exportEmergenciesCsv(filters);
    } catch (e) {
      setExportErr(
        e instanceof ApiError
          ? e.message
          : "Could not export the CSV — please try again.",
      );
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="page-body">
      <PageHeader
        title="Emergencies"
        subtitle={item?.subtitle ?? "Emergency history for your fleet"}
      >
        <Button
          title="Export CSV"
          icon="download"
          tone="quiet"
          loading={exporting}
          onClick={() => void exportCsv()}
        />
      </PageHeader>

      {exportErr && <InlineError error={exportErr} fallback="Could not export the CSV." />}

      <div className="admin-toolbar">
        <SelectField
          label="Status"
          value={status}
          onChange={changeStatus}
          options={STATUS_OPTIONS}
        />
        <div className="field" style={{ minHeight: 46, minWidth: 170 }}>
          <div className="field-body">
            <label className="field-label" htmlFor="hemg-from-filter">
              From date
            </label>
            <input
              id="hemg-from-filter"
              className="field-input"
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
            <label className="field-label" htmlFor="hemg-to-filter">
              To date
            </label>
            <input
              id="hemg-to-filter"
              className="field-input"
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
          options={[
            { value: "", label: "All ambulances" },
            ...(ambulances.data ?? []).map((a) => ({
              value: a.id,
              label: a.vehicle_no,
            })),
          ]}
        />
        <SelectField
          label="Junction"
          value={junctionId}
          onChange={(v) => {
            setJunctionId(v);
            setOffset(0);
          }}
          options={[
            { value: "", label: "All junctions" },
            ...(junctions.data ?? []).map((j) => ({
              value: j.id,
              label: j.name,
            })),
          ]}
        />
        {filterCount > 0 && (
          <Button
            title="Clear filters"
            tone="quiet"
            onClick={() => {
              setStatus("");
              setFrom("");
              setTo("");
              setAmbulanceId("");
              setJunctionId("");
              setOffset(0);
            }}
          />
        )}
        <FreshnessCaption updatedAt={emergencies.dataUpdatedAt} />
      </div>
      <StaleBanner stale={stale} />

      {emergencies.error && rows.length > 0 && (
        <InlineError
          error={emergencies.error}
          fallback="Could not refresh emergencies — showing the last loaded rows."
        />
      )}

      {emergencies.isLoading ? (
        <Loading label="Loading emergencies" />
      ) : emergencies.error && rows.length === 0 ? (
        <InlineError error={emergencies.error} fallback="Could not load emergencies." />
      ) : rows.length === 0 ? (
        <Empty
          icon="emergency"
          title="No emergencies found"
          body="Emergency records for your ambulances appear here as your fleet responds to calls."
        />
      ) : (
        <>
          <Table
            rows={rows}
            keyOf={(row) => row.id}
            onRowClick={(row) => setSelected(row)}
            columns={[
              {
                key: "started_at",
                header: "Started",
                render: (row) => fmtDateTime(row.started_at),
              },
              {
                key: "status",
                header: "Status",
                render: (row) => (
                  <Badge label={row.status} tone={statusBadgeTone(row.status)} />
                ),
              },
              {
                key: "driver_email",
                header: "Driver",
                render: (row) => row.driver_email ?? "—",
              },
              {
                key: "ambulance_vehicle_no",
                header: "Ambulance",
                render: (row) => row.ambulance_vehicle_no ?? "—",
              },
              {
                key: "duration",
                header: "Duration",
                align: "right",
                render: (row) => durationText(row),
              },
            ]}
          />
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 10,
            }}
          >
            <Txt muted>
              Page {page} · showing{" "}
              {total != null
                ? `${offset + 1}–${offset + rows.length} of ${total}`
                : `${offset + 1}–${offset + rows.length}`}
            </Txt>
            <div style={{ display: "flex", gap: 9 }}>
              <Button
                title="Previous"
                tone="quiet"
                disabled={!canPrev}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              />
              <Button
                title="Next"
                tone="quiet"
                disabled={!canNext}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              />
            </div>
          </div>
        </>
      )}

      <Drawer
        open={selected !== null}
        title={selected ? selected.ambulance_vehicle_no ?? "Emergency" : "Emergency"}
        onClose={() => setSelected(null)}
      >
        {selected && <HospitalEmergencyDetail key={selected.id} row={selected} />}
      </Drawer>
    </div>
  );
}

function durationText(row: EmergencyRow): string {
  if (row.started_at && row.ended_at) {
    const minutes = durationMinutes(row.started_at, row.ended_at);
    return minutes === null ? "—" : `${minutes} min`;
  }
  if (row.status.toUpperCase() === "ACTIVE") return "in progress";
  return "—";
}

/** Timeline drawer (contract §4 — the owning hospital can read the timeline). */
function HospitalEmergencyDetail({ row }: { row: EmergencyRow }) {
  const timeline = useQuery({
    queryKey: ["timeline", row.id],
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
      <Badge label={row.status} tone={statusBadgeTone(row.status)} />
      <Card style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <Txt muted style={{ fontSize: 12, textTransform: "uppercase", fontWeight: 600 }}>
          Driver
        </Txt>
        <Txt>{row.driver_email ?? "—"}</Txt>
        <Txt muted style={{ fontSize: 12, textTransform: "uppercase", fontWeight: 600 }}>
          Started
        </Txt>
        <Txt>{fmtDateTime(row.started_at)}</Txt>
        <Txt muted style={{ fontSize: 12, textTransform: "uppercase", fontWeight: 600 }}>
          Ended
        </Txt>
        <Txt>
          {fmtDateTime(row.ended_at)}
          {row.ended_reason ? ` · ${row.ended_reason}` : ""}
        </Txt>
      </Card>

      <SectionTitle>Timeline</SectionTitle>
      {timeline.error ? (
        <InlineError error={timeline.error} fallback="Could not load the timeline." />
      ) : timeline.isLoading ? (
        <Loading label="Loading timeline" />
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
        Acknowledged = the junction device received the command, not that the
        signal changed.
      </Txt>
    </>
  );
}
