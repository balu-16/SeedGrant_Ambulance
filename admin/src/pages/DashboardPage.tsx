/**
 * Role-aware Dashboard (plan §4.1–4.3).
 *
 * ADMIN: Active Emergencies / Fleet / Devices Online / Pending Commands
 * HOSPITAL: fleet at a glance (on-duty, in emergency, drivers, trips today)
 * POLICE: junction state (junctions, priority requested, devices, commands)
 *
 * Phase 2 renders realistic demo values; the stat queries and the activity
 * feed are wired to /admin/* endpoints in phases 2-5.
 */

import { useAuth } from "@/app/auth-context";
import type { PortalRole } from "@/app/nav";
import { Empty, PageHeader, SectionTitle, StatCard } from "@/components/ui";
import type { BadgeTone } from "@/components/ui";

interface StatDef {
  label: string;
  value: string;
  tone: BadgeTone;
  icon: string;
}

interface DashboardDef {
  subtitle: string;
  stats: StatDef[];
  feedTitle: string;
  feedBody: string;
  feedIcon: string;
}

const DASHBOARDS: Record<PortalRole, DashboardDef> = {
  ADMIN: {
    subtitle: "System overview across all junctions, fleets and devices",
    stats: [
      { label: "Active Emergencies", value: "2", tone: "red", icon: "emergency" },
      { label: "Fleet", value: "12", tone: "blue", icon: "local_shipping" },
      { label: "Devices Online", value: "7 / 8", tone: "green", icon: "memory" },
      { label: "Pending Commands", value: "3", tone: "purple", icon: "terminal" },
    ],
    feedTitle: "No recent activity",
    feedBody:
      "System events (emergency starts, command outcomes, device changes) appear here once the portal is wired to the backend in phases 3-5.",
    feedIcon: "history_toggle_off",
  },
  HOSPITAL: {
    subtitle: "Your fleet at a glance — duty state, drivers and emergencies",
    stats: [
      { label: "On-Duty Ambulances", value: "5", tone: "blue", icon: "local_shipping" },
      { label: "In Emergency", value: "1", tone: "red", icon: "emergency" },
      { label: "Drivers on Shift", value: "6", tone: "green", icon: "badge" },
      { label: "Trips Today", value: "9", tone: "purple", icon: "task_alt" },
    ],
    feedTitle: "No fleet activity yet",
    feedBody:
      "Emergency starts and completions for your ambulances appear here once live tracking is wired in phases 3-5.",
    feedIcon: "history_toggle_off",
  },
  POLICE: {
    subtitle: "Your assigned junctions — priority state, devices and commands",
    stats: [
      { label: "My Junctions", value: "3", tone: "blue", icon: "traffic" },
      { label: "Priority Requested", value: "1", tone: "purple", icon: "emergency" },
      { label: "Devices Online", value: "2 / 3", tone: "green", icon: "memory" },
      { label: "Pending Commands", value: "1", tone: "red", icon: "terminal" },
    ],
    feedTitle: "No junction activity yet",
    feedBody:
      "Priority requests and command outcomes at your junctions appear here once the command log is wired in phases 3-5.",
    feedIcon: "history_toggle_off",
  },
};

export function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;
  const def = DASHBOARDS[user.role as PortalRole] ?? DASHBOARDS.ADMIN;

  return (
    <div className="page-body">
      <PageHeader title="Dashboard" subtitle={def.subtitle} />
      <div className="stat-grid">
        {def.stats.map((stat) => (
          <StatCard
            key={stat.label}
            label={stat.label}
            value={stat.value}
            tone={stat.tone}
            icon={stat.icon}
          />
        ))}
      </div>
      <SectionTitle>Recent Activity</SectionTitle>
      <Empty title={def.feedTitle} body={def.feedBody} icon={def.feedIcon} />
    </div>
  );
}
