/**
 * Router.
 *
 * /login is public; everything else lives inside RequireAuth → Shell
 * (navy sidebar + top bar). Pages come from the two persona manifests
 * (adminRoutes.tsx for ADMIN, portalRoutes.tsx for HOSPITAL/POLICE), merged
 * by path: shared paths ("/", "/emergencies", "/fleet", "/devices",
 * "/analytics", "/settings") render a RoleSwitch that picks the entry whose
 * roles include the signed-in user's role, and RoleRoute blocks wrong-role
 * deep links (redirect to "/") exactly like the sidebar hides those items.
 */

import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/app/auth-context";
import { RequireAuth, RoleRoute } from "@/app/RequireAuth";
import { Shell } from "@/app/Shell";
import { rolesForPath, routedPaths } from "@/app/nav";
import { LoginPage } from "@/pages/LoginPage";
import adminRoutes from "@/pages/adminRoutes";
import PERSONA_ROUTES from "@/pages/portalRoutes";

interface RouteEntry {
  element: ReactNode;
  roles: readonly string[];
}

/** path → persona-specific entries, merged from both manifests. */
const ENTRIES_BY_PATH = new Map<string, RouteEntry[]>();
for (const entry of [...adminRoutes, ...PERSONA_ROUTES]) {
  const list = ENTRIES_BY_PATH.get(entry.path) ?? [];
  list.push({ element: entry.element, roles: entry.roles });
  ENTRIES_BY_PATH.set(entry.path, list);
}

/** Renders the manifest entry matching the signed-in role for a shared path. */
function RoleSwitch({ entries }: { entries: RouteEntry[] }) {
  const { user } = useAuth();
  const match = entries.find((e) => e.roles.includes(user?.role ?? ""));
  if (!match) return <Navigate to="/" replace />;
  return <>{match.element}</>;
}

const ROUTE_PATHS = routedPaths();

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Shell />
          </RequireAuth>
        }
      >
        {ROUTE_PATHS.map((to) => {
          const entries = ENTRIES_BY_PATH.get(to);
          if (!entries) return null;
          return (
            <Route
              key={to}
              path={to === "/" ? undefined : to.slice(1)}
              index={to === "/"}
              element={
                <RoleRoute roles={rolesForPath(to)}>
                  <RoleSwitch entries={entries} />
                </RoleRoute>
              }
            />
          );
        })}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
