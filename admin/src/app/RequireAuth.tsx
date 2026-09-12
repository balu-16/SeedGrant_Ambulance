/**
 * Route guards.
 *
 * RequireAuth — unauthenticated visitors are redirected to /login (remembering
 * where they wanted to go). RoleRoute — wrong-role deep links are blocked by
 * redirecting to the user's own dashboard (the sidebar already hides those
 * items for the role).
 */

import type { PropsWithChildren, ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/app/auth-context";
import { homeFor } from "@/app/nav";
import type { Role } from "@/types/api";

export function BootScreen() {
  return (
    <div className="boot" role="status" aria-label="Loading">
      <span className="spinner" />
    </div>
  );
}

export function RequireAuth({ children }: PropsWithChildren) {
  const { user, booting } = useAuth();
  const location = useLocation();
  if (booting) {
    return <BootScreen />;
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

export function RoleRoute({
  roles,
  children,
}: {
  roles: readonly Role[];
  children: ReactNode;
}) {
  const { user } = useAuth();
  if (!user) {
    // RequireAuth sits above this in the tree; nothing to render mid-redirect.
    return null;
  }
  if (!roles.includes(user.role)) {
    return <Navigate to={homeFor(user.role)} replace />;
  }
  return children;
}
