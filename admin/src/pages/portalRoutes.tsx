/**
 * HOSPITAL + POLICE route manifest (plan §4.2/§4.3).
 *
 * Default-exports the persona routes for the orchestrator merge into App.tsx:
 * each entry's `path` matches the nav.ts entry for that role exactly, and
 * `roles` carries the non-ADMIN roles the path serves (ADMIN routes come from
 * the parallel admin manifest). Shared paths ("/" and "/settings") render a
 * role-aware wrapper (shared/PersonaSwitch) so each persona gets its own page.
 */

import type { ReactNode } from "react";
import { HospitalLiveTrackingPage } from "@/pages/hospital/LiveTrackingPage";
import { HospitalFleetPage } from "@/pages/hospital/FleetPage";
import { HospitalDriversPage } from "@/pages/hospital/DriversPage";
import { HospitalEmergenciesPage } from "@/pages/hospital/EmergenciesPage";
import { HospitalAlertsPage } from "@/pages/hospital/AlertsPage";
import { PoliceJunctionLivePage } from "@/pages/police/JunctionLivePage";
import { PoliceCommandLogPage } from "@/pages/police/CommandLogPage";
import { PoliceDeviceHealthPage } from "@/pages/police/DeviceHealthPage";
import { PoliceAnalyticsPage } from "@/pages/police/AnalyticsPage";
import { PersonaDashboard, PersonaSettings } from "@/pages/shared/PersonaSwitch";

export type PersonaRole = "hospital" | "police";

export interface PortalRoute {
  path: string;
  element: ReactNode;
  roles: PersonaRole[];
}

const PERSONA_ROUTES = [
  { path: "/", element: <PersonaDashboard />, roles: ["hospital", "police"] },
  // ---- HOSPITAL ----
  { path: "/tracking", element: <HospitalLiveTrackingPage />, roles: ["hospital"] },
  { path: "/emergencies", element: <HospitalEmergenciesPage />, roles: ["hospital"] },
  { path: "/fleet", element: <HospitalFleetPage />, roles: ["hospital"] },
  { path: "/drivers", element: <HospitalDriversPage />, roles: ["hospital"] },
  { path: "/alerts", element: <HospitalAlertsPage />, roles: ["hospital"] },
  { path: "/settings", element: <PersonaSettings />, roles: ["hospital", "police"] },
  // ---- POLICE ----
  { path: "/junctions", element: <PoliceJunctionLivePage />, roles: ["police"] },
  { path: "/devices", element: <PoliceDeviceHealthPage />, roles: ["police"] },
  { path: "/analytics", element: <PoliceAnalyticsPage />, roles: ["police"] },
  { path: "/commands", element: <PoliceCommandLogPage />, roles: ["police"] },
] satisfies PortalRoute[];

export default PERSONA_ROUTES;
