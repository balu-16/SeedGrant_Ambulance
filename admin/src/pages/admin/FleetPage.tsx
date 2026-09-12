/**
 * ADMIN Fleet (plan §4.1) — all ambulances with hospital/driver lookups;
 * register (createAmbulance) and edit (patchAmbulance: vehicle no, hospital,
 * on-duty toggle, driver assign/detach) via drawers.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createAmbulance,
  listAmbulances,
  listFleetDrivers,
  listHospitals,
  patchAmbulance,
} from "@/services/portal";
import type { Ambulance } from "@/types/portal";
import { statusTone } from "@/components/helpers";
import {
  Badge,
  Button,
  Drawer,
  Empty,
  Field,
  PageHeader,
  Table,
  Txt,
  type TableColumn,
} from "@/components/ui";
import { errMsg, shortId } from "@/pages/admin/shared";
import {
  CheckRow,
  ErrorCard,
  LoadingBlock,
  MiniButton,
  SelectField,
} from "@/pages/admin/widgets";
import "@/pages/admin/admin.css";

export function FleetPage() {
  const ambulances = useQuery({
    queryKey: ["admin", "ambulances"],
    queryFn: listAmbulances,
  });
  const hospitals = useQuery({
    queryKey: ["admin", "hospitals"],
    queryFn: listHospitals,
  });
  const drivers = useQuery({
    queryKey: ["admin", "fleet-drivers"],
    queryFn: listFleetDrivers,
  });

  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Ambulance | null>(null);

  const hospitalNames = new Map(
    (hospitals.data ?? []).map((h) => [h.id, h.name]),
  );
  const driverEmails = new Map(
    (drivers.data ?? []).map((d) => [d.driver_id, d.email ?? d.driver_id]),
  );

  const columns: TableColumn<Ambulance>[] = [
    {
      key: "vehicle_no",
      header: "Vehicle",
      render: (a) => <Txt style={{ fontWeight: 600 }}>{a.vehicle_no}</Txt>,
    },
    {
      key: "hospital",
      header: "Hospital",
      render: (a) =>
        a.hospital_id
          ? (hospitalNames.get(a.hospital_id) ?? shortId(a.hospital_id))
          : "—",
    },
    {
      key: "driver",
      header: "Driver",
      render: (a) =>
        a.driver_id
          ? (driverEmails.get(a.driver_id) ?? shortId(a.driver_id))
          : "—",
    },
    {
      key: "on_duty",
      header: "On duty",
      render: (a) => (
        <Badge
          label={a.on_duty ? "ON_DUTY" : "OFF_DUTY"}
          tone={statusTone(a.on_duty ? "ON_DUTY" : "OFF_DUTY")}
        />
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (a) => <MiniButton title="Edit" onClick={() => setEditing(a)} />,
    },
  ];

  return (
    <div className="page-body">
      <PageHeader
        title="Fleet"
        subtitle="All ambulances, drivers and on-duty status"
      >
        <Button
          title="New ambulance"
          icon="local_shipping"
          onClick={() => setCreating(true)}
        />
      </PageHeader>

      {ambulances.isError ? (
        <ErrorCard
          title="Could not load the fleet"
          error={ambulances.error}
          onRetry={() => void ambulances.refetch()}
        />
      ) : ambulances.isLoading ? (
        <LoadingBlock label="Loading fleet" />
      ) : (
        <Table
          columns={columns}
          rows={ambulances.data ?? []}
          keyOf={(a) => a.id}
          emptyFallback={
            <Empty
              icon="local_shipping"
              title="No ambulances registered"
              body="Register your first ambulance, then assign it to a hospital and a driver."
            />
          }
        />
      )}

      <FleetDrawer open={creating} onClose={() => setCreating(false)} />
      <FleetDrawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        initial={editing ?? undefined}
      />
    </div>
  );
}

/** Drawer wrapper — the form remounts on every open, so fields start clean. */
function FleetDrawer({
  open,
  onClose,
  initial,
}: {
  open: boolean;
  onClose: () => void;
  initial?: Ambulance;
}) {
  return (
    <Drawer
      open={open}
      title={initial ? "Edit ambulance" : "New ambulance"}
      onClose={onClose}
      width={440}
    >
      {open && (
        <FleetForm key={initial?.id ?? "new"} initial={initial} onClose={onClose} />
      )}
    </Drawer>
  );
}

function FleetForm({
  initial,
  onClose,
}: {
  initial?: Ambulance;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const hospitals = useQuery({
    queryKey: ["admin", "hospitals"],
    queryFn: listHospitals,
  });
  const drivers = useQuery({
    queryKey: ["admin", "fleet-drivers"],
    queryFn: listFleetDrivers,
  });

  const [vehicleNo, setVehicleNo] = useState(initial?.vehicle_no ?? "");
  const [hospitalId, setHospitalId] = useState(initial?.hospital_id ?? "");
  const [driverId, setDriverId] = useState(initial?.driver_id ?? "");
  const [onDuty, setOnDuty] = useState(initial?.on_duty ?? false);
  const [err, setErr] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () => {
      const vehicle = vehicleNo.trim();
      if (!vehicle) throw new Error("Vehicle number is required.");
      if (initial) {
        return patchAmbulance(initial.id, {
          vehicle_no: vehicle,
          hospital_id: hospitalId || undefined,
          on_duty: onDuty,
          driver_id: driverId === "" ? null : driverId,
        });
      }
      return createAmbulance({
        vehicle_no: vehicle,
        ...(hospitalId ? { hospital_id: hospitalId } : {}),
        ...(driverId ? { driver_id: driverId } : {}),
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin", "ambulances"] });
      void qc.invalidateQueries({ queryKey: ["admin", "fleet-drivers"] });
      onClose();
    },
    onError: (e) => setErr(errMsg(e)),
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setErr(null);
        m.mutate();
      }}
      style={{ display: "flex", flexDirection: "column", gap: 14 }}
    >
      <Field
        label="Vehicle number"
        icon="local_shipping"
        value={vehicleNo}
        onChange={(e) => setVehicleNo(e.target.value)}
        placeholder="KA-01-AB-1234"
      />

      <SelectField label="Hospital" value={hospitalId} onChange={setHospitalId}>
        <option value="">— Select hospital —</option>
        {(hospitals.data ?? []).map((h) => (
          <option key={h.id} value={h.id}>
            {h.name}
          </option>
        ))}
      </SelectField>

      <SelectField label="Driver" value={driverId} onChange={setDriverId}>
        <option value="">
          {initial ? "— Detach driver —" : "— No driver —"}
        </option>
        {(drivers.data ?? []).map((d) => (
          <option key={d.driver_id} value={d.driver_id}>
            {d.email ?? d.driver_id}
          </option>
        ))}
      </SelectField>
      <Txt muted>
        Drivers listed here are portal accounts already linked to the fleet;
        picking one reassigns this ambulance to that driver, "detach" clears
        the assignment.
      </Txt>

      {initial && (
        <CheckRow label="On duty" checked={onDuty} onChange={setOnDuty} />
      )}

      {err && (
        <div className="admin-inline-error" role="alert">
          {err}
        </div>
      )}

      <Button
        type="submit"
        title={initial ? "Save changes" : "Register ambulance"}
        block
        loading={m.isPending}
      />
    </form>
  );
}
