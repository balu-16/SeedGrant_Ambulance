/**
 * Role-aware navigation config (plan §4).
 *
 * Shared paths appear once per role so each persona gets its own label
 * (e.g. "/junctions" → "Junctions" for ADMIN, "My Junctions" for POLICE).
 * The sidebar renders `navFor(role)`; the router derives each route's
 * allowed roles with `rolesForPath`.
 */

import type { Role } from "@/types/api";

export type PortalRole = Exclude<Role, "DRIVER">;

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
    roles: ["ADMIN", "HOSPITAL", "POLICE"],
    subtitle: "Overview of the emergency priority system",
  },
  // ---- ADMIN ----
  {
    to: "/map",
    label: "Live Map",
    icon: "map",
    roles: ["ADMIN"],
    subtitle: "Active emergencies and junction states on one map",
  },
  {
    to: "/emergencies",
    label: "Emergencies",
    icon: "emergency",
    roles: ["ADMIN", "HOSPITAL"],
    subtitle: "Emergency history with event timelines and exports",
  },
  {
    to: "/users",
    label: "Users",
    icon: "group",
    roles: ["ADMIN"],
    subtitle: "Portal accounts, roles and scope assignments",
  },
  {
    to: "/hospitals",
    label: "Hospitals",
    icon: "local_hospital",
    roles: ["ADMIN"],
    subtitle: "Hospital registry and ambulance assignment",
  },
  {
    to: "/junctions",
    label: "Junctions",
    icon: "traffic",
    roles: ["ADMIN"],
    subtitle: "Junctions, approaches and signal configuration",
  },
  {
    to: "/junctions",
    label: "My Junctions",
    icon: "traffic",
    roles: ["POLICE"],
    subtitle: "Junctions assigned to you and their live state",
  },
  {
    to: "/devices",
    label: "Devices",
    icon: "memory",
    roles: ["ADMIN"],
    subtitle: "Registered Pi devices, keys and heartbeats",
  },
  {
    to: "/devices",
    label: "Device Health",
    icon: "monitor_heart",
    roles: ["POLICE"],
    subtitle: "Online state, heartbeats and telemetry of your devices",
  },
  {
    to: "/fleet",
    label: "Fleet",
    icon: "local_shipping",
    roles: ["ADMIN"],
    subtitle: "All ambulances, drivers and on-duty status",
  },
  {
    to: "/fleet",
    label: "My Fleet",
    icon: "local_shipping",
    roles: ["HOSPITAL"],
    subtitle: "Your ambulances, drivers and on-duty status",
  },
  {
    to: "/analytics",
    label: "Analytics",
    icon: "monitoring",
    roles: ["ADMIN", "POLICE"],
    subtitle: "Crossing times, command outcomes and peak hours",
  },
  {
    to: "/audit",
    label: "Audit",
    icon: "receipt_long",
    roles: ["ADMIN"],
    subtitle: "Every audited action with actor and filters",
  },
  {
    to: "/system",
    label: "System",
    icon: "dns",
    roles: ["ADMIN"],
    subtitle: "Sweeps, config checks, retention and MQTT health",
  },
  // ---- HOSPITAL ----
  {
    to: "/tracking",
    label: "Live Tracking",
    icon: "my_location",
    roles: ["HOSPITAL"],
    subtitle: "Your active emergencies, live positions and priority state",
  },
  {
    to: "/drivers",
    label: "Drivers",
    icon: "badge",
    roles: ["HOSPITAL"],
    subtitle: "Drivers linked to your hospital and their activity",
  },
  {
    to: "/alerts",
    label: "Alerts",
    icon: "notifications_active",
    roles: ["HOSPITAL"],
    subtitle: "Fleet emergency, timeout and device-offline alerts",
  },
  {
    to: "/settings",
    label: "Settings",
    icon: "settings",
    roles: ["HOSPITAL", "POLICE"],
    subtitle: "Profile, password and notification preferences",
  },
  // ---- POLICE ----
  {
    to: "/commands",
    label: "Command Log",
    icon: "terminal",
    roles: ["POLICE"],
    subtitle: "Commands for your junctions with status and retries",
  },
];

export function navFor(role: PortalRole): NavItem[] {
  return NAV_ITEMS.filter((item) => item.roles.includes(role));
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
  role: PortalRole,
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
