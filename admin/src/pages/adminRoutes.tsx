/**
 * ADMIN route manifest — paths mirror src/app/nav.ts exactly (the "/" index
 * plus every ADMIN-only item). The orchestrator merges these into App.tsx:
 * each element is wrapped in RequireAuth/RoleRoute with route.roles there.
 *
 * The "/" dashboard entry maps to the real admin DashboardPage; the shared
 * src/pages/DashboardPage.tsx stays for HOSPITAL/POLICE until their agents
 * land.
 */

import type { ReactNode } from "react";
import { AnalyticsPage } from "@/pages/admin/AnalyticsPage";
import { AuditPage } from "@/pages/admin/AuditPage";
import { DashboardPage } from "@/pages/admin/DashboardPage";
import { DevicesPage } from "@/pages/admin/DevicesPage";
import { EmergenciesPage } from "@/pages/admin/EmergenciesPage";
import { FleetPage } from "@/pages/admin/FleetPage";
import { HospitalsPage } from "@/pages/admin/HospitalsPage";
import { JunctionsPage } from "@/pages/admin/JunctionsPage";
import { LiveMapPage } from "@/pages/admin/LiveMapPage";
import { SystemPage } from "@/pages/admin/SystemPage";
import { UsersPage } from "@/pages/admin/UsersPage";

export interface AdminRoute {
  path: string;
  element: ReactNode;
  roles: ["ADMIN"];
}

const adminRoutes: AdminRoute[] = [
  { path: "/", element: <DashboardPage />, roles: ["ADMIN"] },
  { path: "/map", element: <LiveMapPage />, roles: ["ADMIN"] },
  { path: "/emergencies", element: <EmergenciesPage />, roles: ["ADMIN"] },
  { path: "/users", element: <UsersPage />, roles: ["ADMIN"] },
  { path: "/hospitals", element: <HospitalsPage />, roles: ["ADMIN"] },
  { path: "/junctions", element: <JunctionsPage />, roles: ["ADMIN"] },
  { path: "/devices", element: <DevicesPage />, roles: ["ADMIN"] },
  { path: "/fleet", element: <FleetPage />, roles: ["ADMIN"] },
  { path: "/analytics", element: <AnalyticsPage />, roles: ["ADMIN"] },
  { path: "/audit", element: <AuditPage />, roles: ["ADMIN"] },
  { path: "/system", element: <SystemPage />, roles: ["ADMIN"] },
];

export default adminRoutes;
