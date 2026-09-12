/**
 * POLICE Device Health (plan §4.3) — one card per junction device scoped to
 * the officer's junctions: online badge and last heartbeat; selecting a card
 * opens a telemetry Drawer for that device's junction. Polls every 10s.
 */

import { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { Badge, Card, Drawer, PageHeader, Txt } from "@/components/ui";
import { listDevices, listJunctions, listTelemetry } from "@/services/portal";
import type { DeviceStatus } from "@/types/portal";
import { Loading, InlineError } from "@/pages/shared/bits";
import { fmtDateTime, fmtRelative } from "@/pages/shared/format";

const LIVE_REFRESH = 10_000;

export function PoliceDeviceHealthPage() {
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

  const nameByJunction = new Map(
    (junctions.data ?? []).map((j) => [j.id, j.name]),
  );
  const mine = (devices.data ?? []).filter((d) => junctionIds.includes(d.junction_id));

  const [selected, setSelected] = useState<DeviceStatus | null>(null);
  // Keep the drawer stable across 10s refetches: re-resolve by id.
  const active: DeviceStatus | null =
    mine.find((d) => d.id === selected?.id) ?? null;

  const telemetry = useQuery({
    queryKey: ["telemetry", active?.junction_id ?? "", 20],
    queryFn: () => listTelemetry(active!.junction_id, 20),
    enabled: active !== null,
    refetchInterval: LIVE_REFRESH,
  });

  return (
    <div className="page-body">
      <PageHeader
        title="Device Health"
        subtitle={item?.subtitle ?? "Online state, heartbeats and telemetry of your devices"}
      />

      {(devices.error || junctions.error) && (
        <InlineError
          error={devices.error ?? junctions.error}
          fallback="Could not load device status."
        />
      )}

      {devices.isLoading || junctions.isLoading ? (
        <Loading label="Loading devices" />
      ) : mine.length === 0 ? (
        <Txt muted>
          No devices registered for your junctions yet — ask an administrator.
        </Txt>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 12,
          }}
        >
          {mine.map((device) => (
            <div
              key={device.id}
              role="button"
              tabIndex={0}
              onClick={() => setSelected(device)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setSelected(device);
                }
              }}
              style={{ cursor: "pointer", borderRadius: "var(--radius-card)" }}
            >
              <Card
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                  }}
                >
                  <Txt style={{ fontWeight: 700, fontSize: 16 }}>
                    {nameByJunction.get(device.junction_id) ?? device.junction_id}
                  </Txt>
                  <Badge
                    label={device.online ? "ONLINE" : "OFFLINE"}
                    tone={device.online ? "green" : "red"}
                  />
                </div>
                <Txt muted>
                  last heartbeat: {fmtRelative(device.last_seen)}
                </Txt>
                <Txt muted style={{ fontSize: 12 }}>
                  {fmtDateTime(device.last_seen)} · tap for telemetry
                </Txt>
              </Card>
            </div>
          ))}
        </div>
      )}

      <Drawer
        open={active !== null}
        title={
          active
            ? `Telemetry — ${nameByJunction.get(active.junction_id) ?? active.junction_id}`
            : "Telemetry"
        }
        onClose={() => setSelected(null)}
      >
        {active && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <Badge
                label={active.online ? "ONLINE" : "OFFLINE"}
                tone={active.online ? "green" : "red"}
              />
              <Txt muted>last heartbeat {fmtRelative(active.last_seen)}</Txt>
            </div>
            {telemetry.isLoading ? (
              <Loading label="Loading telemetry" />
            ) : telemetry.error ? (
              <InlineError error={telemetry.error} fallback="Could not load telemetry." />
            ) : (telemetry.data ?? []).length === 0 ? (
              <Txt muted>No telemetry received yet.</Txt>
            ) : (
              (telemetry.data ?? []).map((row) => (
                <Card key={row.id} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <Txt muted style={{ fontSize: 12 }}>
                    {fmtDateTime(row.created_at)}
                  </Txt>
                  <pre
                    style={{
                      margin: 0,
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                      fontSize: 12,
                      lineHeight: 18,
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-all",
                      color: "var(--heading)",
                    }}
                  >
                    {JSON.stringify(row.payload)}
                  </pre>
                </Card>
              ))
            )}
          </>
        )}
      </Drawer>
    </div>
  );
}
