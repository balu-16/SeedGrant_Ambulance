/**
 * ADMIN route manifest — paths mirror src/app/nav.ts exactly (the "/" index
 * plus every ADMIN-only item). The orchestrator merges these into App.tsx:
 * each element is wrapped in RequireAuth/RoleRoute with route.roles there.
 *
 * Heavy routes (leaflet map, audit/system/devices tables, analytics) come
 * from pages/admin/routes-lazy.tsx (React.lazy split, plan §3.4) — App.tsx
 * provides the Suspense fallback, so /login and the dashboards stay eager.
 */

import type { ReactNode } from "react";
import { DashboardPage } from "@/pages/admin/DashboardPage";
import { EmergenciesPage } from "@/pages/admin/EmergenciesPage";
import { FleetPage } from "@/pages/admin/FleetPage";
import { HospitalsPage } from "@/pages/admin/HospitalsPage";
import { JunctionsPage } from "@/pages/admin/JunctionsPage";
import { UsersPage } from "@/pages/admin/UsersPage";
import {
  LazyAnalyticsPage,
  LazyAuditPage,
  LazyDevicesPage,
  LazyLiveMapPage,
  LazySystemPage,
} from "@/pages/admin/routes-lazy";

export interface AdminRoute {
  path: string;
  element: ReactNode;
  roles: ["admin"];
}

const adminRoutes: AdminRoute[] = [
  { path: "/", element: <DashboardPage />, roles: ["admin"] },
  { path: "/map", element: <LazyLiveMapPage />, roles: ["admin"] },
  { path: "/emergencies", element: <EmergenciesPage />, roles: ["admin"] },
  { path: "/users", element: <UsersPage />, roles: ["admin"] },
  { path: "/hospitals", element: <HospitalsPage />, roles: ["admin"] },
  { path: "/junctions", element: <JunctionsPage />, roles: ["admin"] },
  { path: "/devices", element: <LazyDevicesPage />, roles: ["admin"] },
  { path: "/fleet", element: <FleetPage />, roles: ["admin"] },
  { path: "/analytics", element: <LazyAnalyticsPage />, roles: ["admin"] },
  { path: "/audit", element: <LazyAuditPage />, roles: ["admin"] },
  { path: "/system", element: <LazySystemPage />, roles: ["admin"] },
];

export default adminRoutes;
