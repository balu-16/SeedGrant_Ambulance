/**
 * Route guards.
 *
 * RequireAuth — unauthenticated visitors are redirected to /login (remembering
 * where they wanted to go); a boot that could not reach the server shows a
 * retry screen instead of the spinner. RoleRoute — wrong-role deep links are
 * blocked by redirecting to the user's own dashboard (the sidebar already
 * hides those items for the role).
 */

import type { PropsWithChildren, ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/app/auth-context";
import { homeFor } from "@/app/nav";
import { Button, Card, Icon, Txt } from "@/components/ui";
import type { Role } from "@/types/api";

export function BootScreen() {
  return (
    <div className="boot" role="status" aria-label="Loading">
      <span className="spinner" />
    </div>
  );
}

/** Boot could not reach the server (network error ≠ signed-out). */
export function BootErrorScreen({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="boot">
      <Card className="empty" style={{ maxWidth: 420 }}>
        <Icon name="wifi_off" size={42} color="var(--red)" />
        <Txt as="div" className="empty-title">
          Can&apos;t reach the server
        </Txt>
        <Txt muted className="empty-body">
          {message}
        </Txt>
        <Button title="Retry" icon="refresh" onClick={onRetry} />
      </Card>
    </div>
  );
}

export function RequireAuth({ children }: PropsWithChildren) {
  const { user, booting, bootError, retryBoot } = useAuth();
  const location = useLocation();
  if (booting) {
    return bootError ? (
      <BootErrorScreen message={bootError} onRetry={retryBoot} />
    ) : (
      <BootScreen />
    );
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
  const have = user.role.trim().toLowerCase();
  if (!roles.map((r) => r.trim().toLowerCase()).includes(have)) {
    return <Navigate to={homeFor(user.role)} replace />;
  }
  return children;
}
