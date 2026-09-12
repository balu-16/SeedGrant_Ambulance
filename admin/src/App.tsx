/**
 * Router.
 *
 * /login is public; everything else lives inside RequireAuth → Shell
 * (navy sidebar + top bar). Each route is wrapped in RoleRoute with the
 * union of roles from the nav config, so wrong-role deep links are blocked
 * (redirect to the role's dashboard) just as the sidebar hides those items.
 */

import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth, RoleRoute } from "@/app/RequireAuth";
import { Shell } from "@/app/Shell";
import { rolesForPath, routedPaths } from "@/app/nav";
import { DashboardPage } from "@/pages/DashboardPage";
import { LoginPage } from "@/pages/LoginPage";
import { PlaceholderPage } from "@/pages/PlaceholderPage";

const ROUTE_PATHS = routedPaths().filter((p) => p !== "/");

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
        <Route index element={<DashboardPage />} />
        {ROUTE_PATHS.map((to) => (
          <Route
            key={to}
            path={to.slice(1)}
            element={
              <RoleRoute roles={rolesForPath(to)}>
                <PlaceholderPage />
              </RoleRoute>
            }
          />
        ))}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
