/**
 * Guarded shell layout — left navy sidebar with the SeedGrant logo, role-aware
 * nav (Material Symbols icons) and a bottom user block with logout; top bar
 * with the current page title, Simulation badge (when /portal/status reports
 * DEMO_MODE), role chip and initials avatar (components/ui Header); page
 * content renders through the router Outlet.
 *
 * Narrow screens collapse the sidebar behind a menu toggle (CSS-first in
 * layout.css; the button toggles an overlay without changing the desktop
 * layout).
 */

import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, navFor, type PortalRole } from "@/app/nav";
import { Avatar, Badge, Header, Icon } from "@/components/ui";
import { usePortalStatus } from "@/pages/shared/freshness";

export function Shell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  // Polled once per session (staleTime 60s) — drives the Simulation badge.
  const portalStatus = usePortalStatus();
  const simulation = portalStatus.data?.simulation === true;

  if (!user) return null; // RequireAuth guarantees a user here.

  const role = user.role.trim().toLowerCase() as PortalRole;
  const items = navFor(role);
  const current = currentNavItem(location.pathname, role);

  return (
    <div className={`shell${navOpen ? " shell--nav-open" : ""}`}>
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
              onClick={() => setNavOpen(false)}
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
        <Header title={current?.label ?? "Dashboard"} user={user}>
          <button
            type="button"
            className="sidebar-toggle"
            onClick={() => setNavOpen((v) => !v)}
            aria-expanded={navOpen}
            aria-label={navOpen ? "Close menu" : "Open menu"}
          >
            <Icon name={navOpen ? "close" : "menu"} size={22} color="var(--navy)" />
          </button>
          {simulation && (
            <Badge label="Simulation" tone="blue" />
          )}
        </Header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
