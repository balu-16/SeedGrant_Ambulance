/**
 * Lazily-split ADMIN heavy routes (plan §3.4: leaflet map, audit/system/
 * devices, analytics). Kept in a components-only module so fast refresh and
 * the only-export-components lint rule stay happy; adminRoutes.tsx consumes
 * them. App.tsx wraps the router in <Suspense fallback={<BootScreen/>}>.
 */

import { lazy } from "react";

export const LazyAnalyticsPage = lazy(() =>
  import("@/pages/admin/AnalyticsPage").then((m) => ({
    default: m.AnalyticsPage,
  })),
);

export const LazyAuditPage = lazy(() =>
  import("@/pages/admin/AuditPage").then((m) => ({ default: m.AuditPage })),
);

export const LazyDevicesPage = lazy(() =>
  import("@/pages/admin/DevicesPage").then((m) => ({ default: m.DevicesPage })),
);

export const LazyLiveMapPage = lazy(() =>
  import("@/pages/admin/LiveMapPage").then((m) => ({ default: m.LiveMapPage })),
);

export const LazySystemPage = lazy(() =>
  import("@/pages/admin/SystemPage").then((m) => ({ default: m.SystemPage })),
);
