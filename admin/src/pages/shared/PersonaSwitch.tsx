/**
 * Role-aware page switches for shared paths (plan §4.2/§4.3): "/" renders the
 * persona dashboard, "/settings" the persona settings. Kept in their own
 * component-only file so portalRoutes.tsx stays a pure route manifest (fast
 * refresh / only-export-components).
 */

import { useAuth } from "@/app/auth-context";
import { HospitalDashboardPage } from "@/pages/hospital/DashboardPage";
import { HospitalSettingsPage } from "@/pages/hospital/SettingsPage";
import { PoliceDashboardPage } from "@/pages/police/DashboardPage";
import { PoliceSettingsPage } from "@/pages/police/SettingsPage";

export function PersonaDashboard() {
  const { user } = useAuth();
  if (user?.role === "POLICE") return <PoliceDashboardPage />;
  return <HospitalDashboardPage />;
}

export function PersonaSettings() {
  const { user } = useAuth();
  if (user?.role === "POLICE") return <PoliceSettingsPage />;
  return <HospitalSettingsPage />;
}
