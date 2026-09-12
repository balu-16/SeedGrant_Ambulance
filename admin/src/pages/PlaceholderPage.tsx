/**
 * Placeholder pages for every routed nav item.
 *
 * Each route renders the real PageHeader (role-correct title/subtitle from
 * the nav config) plus an Empty state; real data wiring lands in phases 3-5.
 * The routes already exist and are role-guarded, so deep links behave
 * correctly from day one.
 */

import { useLocation } from "react-router-dom";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { Empty, PageHeader } from "@/components/ui";

/** Per-page copy — "wired in phase N" (plan §6). */
const PHASE_NOTES: Record<string, string> = {
  "/map": "The live OpenStreetMap view (react-leaflet) is wired in phase 3.",
  "/tracking": "Live fleet tracking is wired in phase 4 (HOSPITAL role).",
  "/emergencies": "The emergencies history table and detail drawer are wired in phases 3-4.",
  "/users": "Portal user management is wired in phase 3.",
  "/hospitals": "Hospital CRUD and ambulance assignment are wired in phase 3.",
  "/junctions": "Junction and approach management is wired in phase 3; POLICE manual override arrives in phase 5.",
  "/devices": "Device registration, key rotation and telemetry are wired in phases 3-5.",
  "/fleet": "Fleet management is wired in phases 3-4.",
  "/drivers": "Driver management is wired in phase 4.",
  "/alerts": "The alerts feed and toasts are wired in phase 5.",
  "/analytics": "Analytics aggregates are wired in phases 3-5.",
  "/audit": "The audit log viewer is wired in phase 3.",
  "/system": "System sweeps, config checks and MQTT health are wired in phase 5.",
  "/commands": "The command log and manual override are wired in phase 5.",
  "/settings": "Settings are wired in phases 4-5.",
};

export function PlaceholderPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  if (!user) return null;
  const item = currentNavItem(pathname, user.role as PortalRole);

  return (
    <div className="page-body">
      <PageHeader
        title={item?.label ?? "Coming soon"}
        subtitle={item?.subtitle ?? "This section is not yet available."}
      />
      <Empty
        icon={item?.icon ?? "construction"}
        title={`${item?.label ?? "This page"} is scaffolded`}
        body={
          PHASE_NOTES[pathname] ??
          "This page is wired to live data in phases 3-5."
        }
      />
    </div>
  );
}
