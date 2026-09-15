/**
 * HOSPITAL Fleet ("My Fleet", plan §4.2) — register/edit own ambulances,
 * toggle on-duty, assign/reassign drivers from the fleet-driver directory
 * (or detach with a null driver). Hospital ownership is applied server-side
 * (createAmbulance sends no hospital_id).
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { useLocation } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  Drawer,
  Empty,
  Field,
  PageHeader,
  SectionTitle,
  Table,
  Txt,
} from "@/components/ui";
import type { Ambulance } from "@/types/portal";
import {
  createAmbulance,
  listAmbulances,
  listFleetDrivers,
  patchAmbulance,
} from "@/services/portal";
import { Loading, InlineError, SelectField } from "@/pages/shared/bits";

export function HospitalFleetPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "hospital") as PortalRole);
  const queryClient = useQueryClient();

  const [createOpen, setCreateOpen] = useState(false);
  const [newVehicleNo, setNewVehicleNo] = useState("");
  const [editing, setEditing] = useState<Ambulance | null>(null);
  const [editVehicleNo, setEditVehicleNo] = useState("");
  const [editOnDuty, setEditOnDuty] = useState(false);
  const [editDriverId, setEditDriverId] = useState(""); // "" = no driver (null)
  const [formError, setFormError] = useState<string | null>(null);

  const fleet = useQuery({ queryKey: ["ambulances"], queryFn: listAmbulances });
  const drivers = useQuery({
    queryKey: ["fleet-drivers"],
    queryFn: listFleetDrivers,
  });

  const driverById = new Map(
    (drivers.data ?? []).map((d) => [d.driver_id, d.email ?? d.driver_id]),
  );

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["ambulances"] });
    void queryClient.invalidateQueries({ queryKey: ["fleet-drivers"] });
    void queryClient.invalidateQueries({ queryKey: ["live"] });
  };

  const createMut = useMutation({
    mutationFn: () => createAmbulance({ vehicle_no: newVehicleNo.trim() }),
    onSuccess: () => {
      setCreateOpen(false);
      setNewVehicleNo("");
      setFormError(null);
      invalidate();
    },
    onError: (err) =>
      setFormError(err instanceof Error ? err.message : "Could not register the ambulance."),
  });

  const patchMut = useMutation({
    mutationFn: (aid: string) =>
      patchAmbulance(aid, {
        vehicle_no: editVehicleNo.trim(),
        on_duty: editOnDuty,
        driver_id: editDriverId === "" ? null : editDriverId,
      }),
    onSuccess: () => {
      setEditing(null);
      setFormError(null);
      invalidate();
    },
    onError: (err) =>
      setFormError(err instanceof Error ? err.message : "Could not update the ambulance."),
  });

  const openEdit = (ambulance: Ambulance) => {
    setEditing(ambulance);
    setEditVehicleNo(ambulance.vehicle_no);
    setEditOnDuty(ambulance.on_duty);
    setEditDriverId(ambulance.driver_id ?? "");
    setFormError(null);
  };

  const submitCreate = () => {
    setFormError(null);
    if (!newVehicleNo.trim()) {
      setFormError("Vehicle number is required.");
      return;
    }
    createMut.mutate();
  };

  const submitEdit = () => {
    if (!editing) return;
    setFormError(null);
    if (!editVehicleNo.trim()) {
      setFormError("Vehicle number is required.");
      return;
    }
    patchMut.mutate(editing.id);
  };

  return (
    <div className="page-body">
      <PageHeader
        title="My Fleet"
        subtitle={item?.subtitle ?? "Your ambulances, drivers and on-duty status"}
      >
        <Button title="Register ambulance" icon="add" onClick={() => setCreateOpen(true)} />
      </PageHeader>

      {fleet.error && <InlineError error={fleet.error} fallback="Could not load your fleet." />}

      {fleet.isLoading ? (
        <Loading label="Loading fleet" />
      ) : (fleet.data ?? []).length === 0 ? (
        <Empty
          icon="local_shipping"
          title="No ambulances yet"
          body="Register your first ambulance to start managing the fleet."
        />
      ) : (
        <Table
          rows={fleet.data ?? []}
          keyOf={(a) => a.id}
          columns={[
            {
              key: "vehicle_no",
              header: "Vehicle",
              render: (a) => <Txt style={{ fontWeight: 700 }}>{a.vehicle_no}</Txt>,
            },
            {
              key: "on_duty",
              header: "Duty",
              render: (a) => (
                <Badge
                  label={a.on_duty ? "ON DUTY" : "OFF DUTY"}
                  tone={a.on_duty ? "green" : "neutral"}
                />
              ),
            },
            {
              key: "driver",
              header: "Driver",
              render: (a) =>
                a.driver_id ? (driverById.get(a.driver_id) ?? a.driver_id) : "—",
            },
            {
              key: "actions",
              header: "",
              align: "right",
              render: (a) => (
                <Button
                  title="Edit"
                  tone="quiet"
                  onClick={() => openEdit(a)}
                />
              ),
            },
          ]}
        />
      )}

      {/* ---- Create drawer ---- */}
      <Drawer
        open={createOpen}
        title="Register Ambulance"
        onClose={() => {
          setCreateOpen(false);
          setFormError(null);
        }}
      >
        <Field
          label="Vehicle number"
          icon="local_shipping"
          placeholder="e.g. KA-01-AB-1234"
          value={newVehicleNo}
          onChange={(e) => setNewVehicleNo(e.target.value)}
        />
        <Txt muted>
          The ambulance is registered under your hospital automatically.
        </Txt>
        {formError && <InlineError error={formError} />}
        <Button
          title="Register ambulance"
          icon="check"
          block
          loading={createMut.isPending}
          onClick={submitCreate}
        />
      </Drawer>

      {/* ---- Edit drawer ---- */}
      <Drawer
        open={editing !== null}
        title={editing ? `Edit ${editing.vehicle_no}` : "Edit Ambulance"}
        onClose={() => {
          setEditing(null);
          setFormError(null);
        }}
      >
        {editing && (
          <>
            <Field
              label="Vehicle number"
              icon="local_shipping"
              value={editVehicleNo}
              onChange={(e) => setEditVehicleNo(e.target.value)}
            />
            <Card
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 10,
              }}
            >
              <div>
                <Txt style={{ fontWeight: 600 }}>On duty</Txt>
                <Txt muted style={{ display: "block", fontSize: 12 }}>
                  Ambulances on duty are eligible for emergency dispatch.
                </Txt>
              </div>
              <Badge
                label={editOnDuty ? "ON DUTY" : "OFF DUTY"}
                tone={editOnDuty ? "green" : "neutral"}
              />
              <Button
                title={editOnDuty ? "Set off duty" : "Set on duty"}
                tone="quiet"
                onClick={() => setEditOnDuty((v) => !v)}
              />
            </Card>
            <SectionTitle>Driver</SectionTitle>
            {drivers.isLoading ? (
              <Loading label="Loading drivers" />
            ) : (
              <SelectField
                label="Assigned driver"
                value={editDriverId}
                onChange={setEditDriverId}
                options={[
                  { value: "", label: "— No driver —" },
                  ...(drivers.data ?? []).map((d) => ({
                    value: d.driver_id,
                    label: `${d.email ?? d.driver_id}${
                      d.vehicle_no ? ` (on ${d.vehicle_no})` : ""
                    }`,
                  })),
                ]}
              />
            )}
            {formError && <InlineError error={formError} />}
            <Button
              title="Save changes"
              icon="check"
              block
              loading={patchMut.isPending}
              onClick={submitEdit}
            />
          </>
        )}
      </Drawer>
    </div>
  );
}
