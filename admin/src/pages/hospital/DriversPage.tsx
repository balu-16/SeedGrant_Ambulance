/**
 * HOSPITAL Drivers (plan §4.2) — drivers linked to the hospital (from the
 * fleet-driver directory) with the ambulance they are currently assigned to.
 * Each row links to the fleet page for reassignment.
 */

import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { Empty, PageHeader, Table, Txt } from "@/components/ui";
import { listFleetDrivers } from "@/services/portal";
import { Loading, InlineError } from "@/pages/shared/bits";

export function HospitalDriversPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "hospital") as PortalRole);

  const drivers = useQuery({
    queryKey: ["fleet-drivers"],
    queryFn: listFleetDrivers,
  });

  return (
    <div className="page-body">
      <PageHeader
        title="Drivers"
        subtitle={item?.subtitle ?? "Drivers linked to your hospital and their activity"}
      />

      {drivers.error && (
        <InlineError error={drivers.error} fallback="Could not load drivers." />
      )}

      {drivers.isLoading ? (
        <Loading label="Loading drivers" />
      ) : (drivers.data ?? []).length === 0 ? (
        <Empty
          icon="badge"
          title="No drivers linked yet"
          body="Active driver accounts visible to your hospital appear here, including drivers not yet assigned to an ambulance."
        />
      ) : (
        <Table
          rows={drivers.data ?? []}
          keyOf={(d) => d.driver_id}
          columns={[
            {
              key: "email",
              header: "Driver",
              render: (d) => (
                <Txt style={{ fontWeight: 600 }}>{d.email ?? d.driver_id}</Txt>
              ),
            },
            {
              key: "vehicle_no",
              header: "Assigned vehicle",
              render: (d) => (d.vehicle_no ? d.vehicle_no : "—"),
            },
            {
              key: "link",
              header: "",
              align: "right",
              render: () => (
                <Link to="/fleet" style={{ fontWeight: 600 }}>
                  Manage in Fleet
                </Link>
              ),
            },
          ]}
        />
      )}
    </div>
  );
}
