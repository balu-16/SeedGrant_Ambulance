/**
 * HOSPITAL Emergencies (plan §4.2) — history of the own fleet (server-scoped):
 * status filter, offset pagination and a client-side CSV export (utils/csv)
 * of the currently loaded rows for records/insurance.
 */

import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { useLocation } from "react-router-dom";
import {
  Badge,
  Button,
  Empty,
  PageHeader,
  Table,
  Txt,
} from "@/components/ui";
import { fetchEmergencies } from "@/services/portal";
import type { EmergencyRow } from "@/types/portal";
import { downloadCsv } from "@/utils/csv";
import { Loading, InlineError, SelectField } from "@/pages/shared/bits";
import { durationMinutes, fmtDateTime, statusBadgeTone } from "@/pages/shared/format";

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
  const item = currentNavItem(pathname, (user?.role ?? "HOSPITAL") as PortalRole);

  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);

  const emergencies = useQuery({
    queryKey: ["emergencies", status, offset],
    queryFn: () =>
      fetchEmergencies({
        limit: PAGE_SIZE,
        offset,
        status: status || undefined,
      }),
    placeholderData: keepPreviousData,
  });

  const rows = emergencies.data?.items ?? [];
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const canPrev = offset > 0;
  const canNext = rows.length === PAGE_SIZE;

  const changeStatus = (value: string) => {
    setStatus(value);
    setOffset(0);
  };

  const exportCsv = () => {
    downloadCsv(
      "emergencies.csv",
      rows.map((row) => ({
        id: row.id,
        status: row.status,
        started_at: row.started_at ?? "",
        ended_at: row.ended_at ?? "",
        duration_minutes: durationMinutes(row.started_at, row.ended_at) ?? "",
        driver_email: row.driver_email ?? "",
        ambulance_vehicle_no: row.ambulance_vehicle_no ?? "",
        ended_reason: row.ended_reason ?? "",
      })),
    );
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
          disabled={rows.length === 0}
          onClick={exportCsv}
        />
      </PageHeader>

      <div style={{ maxWidth: 320 }}>
        <SelectField
          label="Status"
          value={status}
          onChange={changeStatus}
          options={STATUS_OPTIONS}
        />
      </div>

      {emergencies.error && (
        <InlineError error={emergencies.error} fallback="Could not load emergencies." />
      )}

      {emergencies.isLoading ? (
        <Loading label="Loading emergencies" />
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
              Page {page} · showing {offset + 1}–{offset + rows.length}
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
