/**
 * Guarded shell layout — left navy sidebar with the SeedGrant logo, role-aware
 * nav (Material Symbols icons) and a bottom user block with logout; top bar
 * with the current page title, role chip and initials avatar (components/ui
 * Header); page content renders through the router Outlet.
 */

import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, navFor, type PortalRole } from "@/app/nav";
import { Avatar, Header, Icon } from "@/components/ui";

export function Shell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  if (!user) return null; // RequireAuth guarantees a user here.

  const role = user.role as PortalRole;
  const items = navFor(role);
  const current = currentNavItem(location.pathname, role);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span className="sidebar-logo-badge">
            <Icon name="emergency" size={26} color="var(--blue)" />
          </span>
          <span>
            <span className="sidebar-logo-name">SeedGrant</span>
            <br />
            <span className="sidebar-logo-sub">Admin Portal</span>
          </span>
        </div>

        <div className="sidebar-section">{role} console</div>
        <nav className="sidebar-nav" aria-label="Primary">
          {items.map((item) => (
            <NavLink
              key={`${item.to}-${item.label}`}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `nav-item${isActive ? " nav-item--active" : ""}`
              }
            >
              <Icon name={item.icon} size={22} color="currentColor" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-user">
          <Avatar name={user.name ?? user.email} size="sm" onDark />
          <span className="sidebar-user-info">
            <span className="sidebar-user-name">
              {user.name ?? user.email.split("@")[0]}
            </span>
            <span className="sidebar-user-email">{user.email}</span>
          </span>
          <button
            type="button"
            className="sidebar-logout"
            onClick={() => {
              void logout();
            }}
            aria-label="Log out"
            title="Log out"
          >
            <Icon name="logout" size={20} color="currentColor" />
          </button>
        </div>
      </aside>

      <div className="main">
        <Header title={current?.label ?? "Dashboard"} user={user} />
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
