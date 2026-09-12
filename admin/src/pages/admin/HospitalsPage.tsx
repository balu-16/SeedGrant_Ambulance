/**
 * ADMIN Hospitals (plan §4.1) — hospital registry with create/edit drawers
 * (name, address, phone, latitude, longitude) via createHospital/patchHospital.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createHospital, listHospitals, patchHospital } from "@/services/portal";
import type { Hospital } from "@/types/portal";
import {
  Button,
  Card,
  Drawer,
  Empty,
  Field,
  Icon,
  PageHeader,
  Txt,
} from "@/components/ui";
import { errMsg, fmtDate } from "@/pages/admin/shared";
import { ErrorCard, LoadingBlock, MiniButton } from "@/pages/admin/widgets";
import "@/pages/admin/admin.css";

export function HospitalsPage() {
  const hospitals = useQuery({
    queryKey: ["admin", "hospitals"],
    queryFn: listHospitals,
  });
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Hospital | null>(null);

  return (
    <div className="page-body">
      <PageHeader
        title="Hospitals"
        subtitle="Hospital registry and ambulance assignment"
      >
        <Button title="New hospital" icon="add_business" onClick={() => setCreating(true)} />
      </PageHeader>

      {hospitals.isError ? (
        <ErrorCard
          title="Could not load hospitals"
          error={hospitals.error}
          onRetry={() => void hospitals.refetch()}
        />
      ) : hospitals.isLoading ? (
        <LoadingBlock label="Loading hospitals" />
      ) : (hospitals.data ?? []).length === 0 ? (
        <Empty
          icon="local_hospital"
          title="No hospitals yet"
          body="Create the first hospital, then assign ambulances and hospital users to it."
        />
      ) : (
        <div className="admin-cards">
          {(hospitals.data ?? []).map((h) => (
            <Card key={h.id}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <Txt as="div" style={{ fontSize: 16, fontWeight: 700 }}>
                    {h.name}
                  </Txt>
                  <Txt muted style={{ marginTop: 4 }}>
                    {h.address ?? "No address on file"}
                  </Txt>
                </span>
                <MiniButton title="Edit" onClick={() => setEditing(h)} />
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  marginTop: 12,
                  flexWrap: "wrap",
                }}
              >
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <Icon name="call" size={16} color="var(--muted)" />
                  <Txt muted>{h.phone ?? "—"}</Txt>
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <Icon name="location_on" size={16} color="var(--muted)" />
                  <Txt muted className="admin-mono">
                    {h.latitude != null && h.longitude != null
                      ? `${h.latitude.toFixed(5)}, ${h.longitude.toFixed(5)}`
                      : "—"}
                  </Txt>
                </span>
              </div>
              <Txt muted className="admin-mono" style={{ display: "block", marginTop: 8 }}>
                added {fmtDate(h.created_at)}
              </Txt>
            </Card>
          ))}
        </div>
      )}

      <HospitalDrawer open={creating} onClose={() => setCreating(false)} />
      <HospitalDrawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        initial={editing ?? undefined}
      />
    </div>
  );
}

/** Drawer wrapper — the form remounts on every open, so fields start clean. */
function HospitalDrawer({
  open,
  onClose,
  initial,
}: {
  open: boolean;
  onClose: () => void;
  initial?: Hospital;
}) {
  return (
    <Drawer
      open={open}
      title={initial ? "Edit hospital" : "New hospital"}
      onClose={onClose}
      width={440}
    >
      {open && (
        <HospitalForm key={initial?.id ?? "new"} initial={initial} onClose={onClose} />
      )}
    </Drawer>
  );
}

function HospitalForm({
  initial,
  onClose,
}: {
  initial?: Hospital;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(initial?.name ?? "");
  const [address, setAddress] = useState(initial?.address ?? "");
  const [phone, setPhone] = useState(initial?.phone ?? "");
  const [latStr, setLatStr] = useState(
    initial?.latitude != null ? String(initial.latitude) : "",
  );
  const [lngStr, setLngStr] = useState(
    initial?.longitude != null ? String(initial.longitude) : "",
  );
  const [err, setErr] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () => {
      const trimmed = name.trim();
      if (!trimmed) throw new Error("Hospital name is required.");
      const lat = latStr.trim() === "" ? undefined : Number(latStr);
      const lng = lngStr.trim() === "" ? undefined : Number(lngStr);
      if (Number.isNaN(lat) || Number.isNaN(lng)) {
        throw new Error("Latitude and longitude must be numbers.");
      }
      if (lat != null && (lat < -90 || lat > 90)) {
        throw new Error("Latitude must be between -90 and 90.");
      }
      if (lng != null && (lng < -180 || lng > 180)) {
        throw new Error("Longitude must be between -180 and 180.");
      }
      const body = {
        name: trimmed,
        address: address.trim() || undefined,
        phone: phone.trim() || undefined,
        latitude: lat,
        longitude: lng,
      };
      return initial ? patchHospital(initial.id, body) : createHospital(body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin", "hospitals"] });
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
        label="Name"
        icon="local_hospital"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="City General Hospital"
      />
      <Field
        label="Address"
        icon="location_on"
        value={address}
        onChange={(e) => setAddress(e.target.value)}
        placeholder="Street, area, city"
      />
      <Field
        label="Phone"
        icon="call"
        type="tel"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        placeholder="+91 …"
      />
      <Field
        label="Latitude"
        icon="explore"
        type="number"
        value={latStr}
        onChange={(e) => setLatStr(e.target.value)}
        placeholder="12.97160"
      />
      <Field
        label="Longitude"
        icon="explore"
        type="number"
        value={lngStr}
        onChange={(e) => setLngStr(e.target.value)}
        placeholder="77.59460"
      />

      {err && (
        <div className="admin-inline-error" role="alert">
          {err}
        </div>
      )}

      <Button
        type="submit"
        title={initial ? "Save changes" : "Create hospital"}
        block
        loading={m.isPending}
      />
    </form>
  );
}
