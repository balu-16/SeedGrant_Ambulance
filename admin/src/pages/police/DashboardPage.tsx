/**
 * POLICE Dashboard (plan §4.3) — one card per assigned junction: current
 * command state (from the live feed) and device online state, with a tap
 * through to the junction live view. Scope = user.junction_ids (server also
 * enforces); polls live state every 10s.
 */

import { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { Badge, Card, Empty, PageHeader, SectionTitle, Txt } from "@/components/ui";
import { fetchLive, listDevices, listJunctions } from "@/services/portal";
import { Loading, InlineError } from "@/pages/shared/bits";
import { statusBadgeTone } from "@/pages/shared/format";

const LIVE_REFRESH = 10_000;

export function PoliceDashboardPage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "POLICE") as PortalRole);

  const junctionIds = useMemo(() => user?.junction_ids ?? [], [user]);

  const junctions = useQuery({ queryKey: ["junctions"], queryFn: listJunctions });
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: listDevices,
    refetchInterval: LIVE_REFRESH,
  });
  const live = useQuery({
    queryKey: ["live"],
    queryFn: fetchLive,
    refetchInterval: LIVE_REFRESH,
  });

  const mine = (junctions.data ?? []).filter((j) => junctionIds.includes(j.id));
  const deviceByJunction = new Map(
    (devices.data ?? []).map((d) => [d.junction_id, d]),
  );

  /** Latest non-terminal command per junction, else the newest command. */
  const commandByJunction = new Map<string, string>();
  for (const session of live.data?.items ?? []) {
    for (const command of session.commands) {
      if (!junctionIds.includes(command.junction_id)) continue;
      commandByJunction.set(command.junction_id, command.status);
    }
  }

  return (
    <div className="page-body">
      <PageHeader
        title="Dashboard"
        subtitle={item?.subtitle ?? "Your assigned junctions and their live state"}
      />

      {(junctions.error || devices.error || live.error) && (
        <InlineError
          error={junctions.error ?? devices.error ?? live.error}
          fallback="Could not load your junctions."
        />
      )}

      {junctions.isLoading ? (
        <Loading label="Loading junctions" />
      ) : mine.length === 0 ? (
        <Empty
          icon="traffic"
          title="No junctions assigned"
          body="Ask an administrator to assign you to junctions — they will appear here with their live state."
        />
      ) : (
        <>
          <SectionTitle>My Junctions</SectionTitle>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 12,
            }}
          >
            {mine.map((junction) => {
              const device = deviceByJunction.get(junction.id);
              const commandStatus = commandByJunction.get(junction.id);
              return (
                <Card
                  key={junction.id}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                  }}
                >
                  <Txt style={{ fontWeight: 700, fontSize: 17 }}>{junction.name}</Txt>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {commandStatus ? (
                      <Badge
                        label={commandStatus}
                        tone={statusBadgeTone(commandStatus)}
                      />
                    ) : (
                      <Badge label="IDLE" tone="neutral" />
                    )}
                    {device ? (
                      <Badge
                        label={device.online ? "DEVICE ONLINE" : "DEVICE OFFLINE"}
                        tone={device.online ? "green" : "red"}
                      />
                    ) : (
                      <Badge label="NO DEVICE" tone="neutral" />
                    )}
                  </div>
                  <Link
                    to={`/junctions?junction=${junction.id}`}
                    style={{ fontWeight: 600, fontSize: 14 }}
                  >
                    Open live view →
                  </Link>
                </Card>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
