/**
 * HOSPITAL Settings (plan §4.2) — read-only hospital profile card (own
 * hospital, scoped server-side) and the shared change-password card.
 * Notification preferences land with the realtime phase.
 */

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { useLocation } from "react-router-dom";
import { Card, Empty, PageHeader, SectionTitle, Txt } from "@/components/ui";
import { listHospitals } from "@/services/portal";
import { Loading, InlineError } from "@/pages/shared/bits";
import { PasswordCard } from "@/pages/shared/PasswordCard";

export function HospitalSettingsPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "hospital") as PortalRole);

  const hospitals = useQuery({ queryKey: ["hospitals"], queryFn: listHospitals });

  const hospital =
    (hospitals.data ?? []).find((h) => h.id === user?.hospital_id) ?? null;

  const rows: { label: string; value: string }[] = hospital
    ? [
        { label: "Name", value: hospital.name },
        { label: "Address", value: hospital.address ?? "—" },
        { label: "Phone", value: hospital.phone ?? "—" },
        {
          label: "Coordinates",
          value:
            hospital.latitude !== null && hospital.longitude !== null
              ? `${hospital.latitude.toFixed(5)}, ${hospital.longitude.toFixed(5)}`
              : "—",
        },
        { label: "Hospital ID", value: hospital.id },
      ]
    : [];

  return (
    <div className="page-body">
      <PageHeader
        title="Settings"
        subtitle={item?.subtitle ?? "Profile, password and notification preferences"}
      />

      <SectionTitle>Hospital Profile</SectionTitle>
      {hospitals.error ? (
        <InlineError error={hospitals.error} fallback="Could not load the hospital profile." />
      ) : hospitals.isLoading ? (
        <Loading label="Loading hospital profile" />
      ) : hospital === null ? (
        <Empty
          icon="local_hospital"
          title="Hospital profile unavailable"
          body="Your account is not linked to a hospital yet — ask an administrator to assign one."
        />
      ) : (
        <Card style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {rows.map((row) => (
            <div
              key={row.label}
              style={{
                display: "flex",
                gap: 14,
                alignItems: "baseline",
                flexWrap: "wrap",
              }}
            >
              <Txt muted style={{ minWidth: 110, fontSize: 12, fontWeight: 600, textTransform: "uppercase" }}>
                {row.label}
              </Txt>
              <Txt>{row.value}</Txt>
            </div>
          ))}
          <Txt muted style={{ fontSize: 12 }}>
            Profile details are managed by the SeedGrant administrator.
          </Txt>
        </Card>
      )}

      <SectionTitle>Password</SectionTitle>
      <PasswordCard />
    </div>
  );
}
