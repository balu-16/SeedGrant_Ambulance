/**
 * POLICE Settings (plan §4.3) — password change (shared PasswordCard, same
 * pattern as the hospital persona). Notification preferences land with the
 * realtime phase.
 */

import { useLocation } from "react-router-dom";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { PageHeader, SectionTitle } from "@/components/ui";
import { PasswordCard } from "@/pages/shared/PasswordCard";

export function PoliceSettingsPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "POLICE") as PortalRole);

  return (
    <div className="page-body">
      <PageHeader
        title="Settings"
        subtitle={item?.subtitle ?? "Profile, password and notification preferences"}
      />
      <SectionTitle>Password</SectionTitle>
      <PasswordCard />
    </div>
  );
}
