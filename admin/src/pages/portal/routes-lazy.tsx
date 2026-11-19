/**
 * Lazily-split HOSPITAL/POLICE heavy routes (plan §3.4: the leaflet-backed
 * pages). Components-only module so fast refresh stays functional;
 * portalRoutes.tsx consumes these. App.tsx provides the Suspense fallback.
 */

import { lazy } from "react";

export const LazyHospitalLiveTrackingPage = lazy(() =>
  import("@/pages/hospital/LiveTrackingPage").then((m) => ({
    default: m.HospitalLiveTrackingPage,
  })),
);

export const LazyPoliceJunctionLivePage = lazy(() =>
  import("@/pages/police/JunctionLivePage").then((m) => ({
    default: m.PoliceJunctionLivePage,
  })),
);
