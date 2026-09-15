/**
 * Role-aware navigation config (plan §4).
 *
 * Shared paths appear once per role so each persona gets its own label
 * (e.g. "/junctions" → "Junctions" for ADMIN, "My Junctions" for POLICE).
 * The sidebar renders `navFor(role)`; the router derives each route's
 * allowed roles with `rolesForPath`.
 */

import type { Role } from "@/types/api";

export type PortalRole = Exclude<Role, "driver">;

function norm(r: string): string {
  return r.trim().toLowerCase();
}

export interface NavItem {
  to: string;
  label: string;
  /** Material Symbols ligature. */
  icon: string;
  roles: PortalRole[];
  /** Page subtitle shown by the page header. */
  subtitle: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  {
    to: "/",
    label: "Dashboard",
    icon: "dashboard",
    roles: ["admin", "hospital", "police"],
    subtitle: "Overview of the emergency priority system",
  },
  // ---- ADMIN ----
  {
    to: "/map",
    label: "Live Map",
    icon: "map",
    roles: ["admin"],
    subtitle: "Active emergencies and junction states on one map",
  },
  {
    to: "/emergencies",
    label: "Emergencies",
    icon: "emergency",
    roles: ["admin", "hospital"],
    subtitle: "Emergency history with event timelines and exports",
  },
  {
    to: "/users",
    label: "Users",
    icon: "group",
    roles: ["admin"],
    subtitle: "Portal accounts, roles and scope assignments",
  },
  {
    to: "/hospitals",
    label: "Hospitals",
    icon: "local_hospital",
    roles: ["admin"],
    subtitle: "Hospital registry and ambulance assignment",
  },
  {
    to: "/junctions",
    label: "Junctions",
    icon: "traffic",
    roles: ["admin"],
    subtitle: "Junctions, approaches and signal configuration",
  },
  {
    to: "/junctions",
    label: "My Junctions",
    icon: "traffic",
    roles: ["police"],
    subtitle: "Junctions assigned to you and their live state",
  },
  {
    to: "/devices",
    label: "Devices",
    icon: "memory",
    roles: ["admin"],
    subtitle: "Registered Pi devices, keys and heartbeats",
  },
  {
    to: "/devices",
    label: "Device Health",
    icon: "monitor_heart",
    roles: ["police"],
    subtitle: "Online state, heartbeats and telemetry of your devices",
  },
  {
    to: "/fleet",
    label: "Fleet",
    icon: "local_shipping",
    roles: ["admin"],
    subtitle: "All ambulances, drivers and on-duty status",
  },
  {
    to: "/fleet",
    label: "My Fleet",
    icon: "local_shipping",
    roles: ["hospital"],
    subtitle: "Your ambulances, drivers and on-duty status",
  },
  {
    to: "/analytics",
    label: "Analytics",
    icon: "monitoring",
    roles: ["admin", "police"],
    subtitle: "Crossing times, command outcomes and peak hours",
  },
  {
    to: "/audit",
    label: "Audit",
    icon: "receipt_long",
    roles: ["admin"],
    subtitle: "Every audited action with actor and filters",
  },
  {
    to: "/system",
    label: "System",
    icon: "dns",
    roles: ["admin"],
    subtitle: "Sweeps, config checks, retention and MQTT health",
  },
  // ---- HOSPITAL ----
  {
    to: "/tracking",
    label: "Live Tracking",
    icon: "my_location",
    roles: ["hospital"],
    subtitle: "Your active emergencies, live positions and priority state",
  },
  {
    to: "/drivers",
    label: "Drivers",
    icon: "badge",
    roles: ["hospital"],
    subtitle: "Drivers linked to your hospital and their activity",
  },
  {
    to: "/alerts",
    label: "Alerts",
    icon: "notifications_active",
    roles: ["hospital"],
    subtitle: "Fleet emergency, timeout and device-offline alerts",
  },
  {
    to: "/settings",
    label: "Settings",
    icon: "settings",
    roles: ["hospital", "police"],
    subtitle: "Profile, password and notification preferences",
  },
  // ---- POLICE ----
  {
    to: "/commands",
    label: "Command Log",
    icon: "terminal",
    roles: ["police"],
    subtitle: "Commands for your junctions with status and retries",
  },
];

export function navFor(role: PortalRole | string): NavItem[] {
  const r = norm(role);
  return NAV_ITEMS.filter((item) =>
    item.roles.map(norm).includes(r),
  );
}

/** Union of roles allowed on a path (across per-role duplicates). */
export function rolesForPath(to: string): PortalRole[] {
  const roles = NAV_ITEMS.filter((item) => item.to === to).flatMap(
    (item) => item.roles,
  );
  return [...new Set(roles)];
}

/** Unique routed paths, in sidebar order ("/" first). */
export function routedPaths(): string[] {
  const seen = new Set<string>();
  for (const item of NAV_ITEMS) {
    seen.add(item.to);
  }
  return [...seen];
}

/** Where a role lands after login / on wrong-role deep links. */
export function homeFor(_role: Role): string {
  // Every persona's home is its role-aware Dashboard at "/".
  return "/";
}

/** Best-match sidebar entry for the current location (used by the top bar). */
export function currentNavItem(
  pathname: string,
  role: PortalRole | string,
): NavItem | undefined {
  const items = navFor(role);
  return (
    items.find((item) => item.to === pathname) ??
    items
      .filter((item) => item.to !== "/" && pathname.startsWith(item.to))
      .sort((a, b) => b.to.length - a.to.length)[0] ??
    items[0]
  );
}
