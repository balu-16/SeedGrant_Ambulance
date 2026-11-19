/**
 * POLICE Junction Live (plan §4.3 "Junction Detail / Live" + "Manual
 * Override") — junction selector, live map with approaching sessions, current
 * command timeline, the override console (FORCE_RELEASE / HOLD / REISSUE with
 * a required reason, results in a local timeline, 409/403 inline) and the
 * telemetry + detection cards. Live cards poll every 10s.
 */

import { useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/app/auth-context";
import { currentNavItem, type PortalRole } from "@/app/nav";
import { ApiError } from "@/services/api";
import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  PageHeader,
  SectionTitle,
  Table,
  Timeline,
  Txt,
} from "@/components/ui";
import {
  fetchLive,
  listDetections,
  listJunctions,
  listTelemetry,
  overrideJunction,
} from "@/services/portal";
import type { OverrideResult } from "@/types/portal";
import {
  FreshnessCaption,
  InlineError,
  Loading,
  SelectField,
  StaleBanner,
} from "@/pages/shared/bits";
import { isStale, useFreshnessThresholds } from "@/pages/shared/freshness";
import { MapView, type MapDot } from "@/pages/shared/MapView";
import {
  DEFAULT_CENTER,
  fmtDateTime,
  fmtRelative,
  statusBadgeTone,
  timelineTone,
  toneColor,
} from "@/pages/shared/format";

const LIVE_REFRESH = 10_000;
type OverrideAction = OverrideResult["action"];

const OVERRIDES: { action: OverrideAction; title: string; tone: "primary" | "quiet" | "danger" }[] = [
  { action: "FORCE_RELEASE", title: "Force release", tone: "danger" },
  { action: "HOLD", title: "Hold priority", tone: "quiet" },
  { action: "REISSUE", title: "Re-issue command", tone: "primary" },
];

export function PoliceJunctionLivePage() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const item = currentNavItem(pathname, (user?.role ?? "police") as PortalRole);
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const thresholds = useFreshnessThresholds();

  const junctionIds = useMemo(() => user?.junction_ids ?? [], [user]);
  const junctions = useQuery({ queryKey: ["junctions"], queryFn: listJunctions });
  const mine = (junctions.data ?? []).filter((j) => junctionIds.includes(j.id));

  const requested = searchParams.get("junction");
  const junction =
    mine.find((j) => j.id === requested) ?? mine[0] ?? null;

  const live = useQuery({
    queryKey: ["live"],
    queryFn: fetchLive,
    refetchInterval: LIVE_REFRESH,
  });
  const stale =
    live.data !== undefined &&
    isStale(live.dataUpdatedAt, thresholds.portalStaleSeconds);

  const junctionId = junction?.id ?? "";
  const telemetry = useQuery({
    queryKey: ["telemetry", junctionId, 12],
    queryFn: () => listTelemetry(junctionId, 12),
    enabled: junctionId !== "",
    refetchInterval: LIVE_REFRESH,
  });
  const detections = useQuery({
    queryKey: ["detections", junctionId],
    queryFn: async () => {
      const res = await listDetections({ junction_id: junctionId, limit: 20 });
      return Array.isArray(res) ? res : res.items;
    },
    enabled: junctionId !== "",
    refetchInterval: LIVE_REFRESH,
  });

  // Sessions approaching/active at this junction (any of their commands
  // reference it) with a known last position.
  const junctionSessions = (live.data?.items ?? []).filter((session) =>
    session.commands.some((c) => c.junction_id === junctionId),
  );
  const dots: MapDot[] = [
    ...(junction && junction.latitude !== null && junction.longitude !== null
      ? [
          {
            id: `junction-${junction.id}`,
            latitude: junction.latitude,
            longitude: junction.longitude,
            color: "var(--navy)",
            title: junction.name,
            detail: "Junction",
          },
        ]
      : []),
    ...junctionSessions
      .filter((s) => s.latest_gps)
      .map((s) => ({
        id: s.id,
        latitude: s.latest_gps!.latitude,
        longitude: s.latest_gps!.longitude,
        color: toneColor(statusBadgeTone(s.status)),
        title: s.ambulance.vehicle_no,
        detail: `${s.driver.email} · ${s.status}`,
      })),
  ];

  const junctionCommands = junctionSessions.flatMap((s) =>
    s.commands.filter((c) => c.junction_id === junctionId),
  );
  // Per-junction live state (contract §5): device health + latest telemetry
  // state; telemetry without a "state" key renders "Unknown".
  const junctionState = live.data?.junction_states[junctionId] ?? null;

  // ---- Override console ----
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLog, setActionLog] = useState<
    {
      title: string;
      meta: string;
      delivery: string | null;
      release: string | null;
      tone: "green" | "red" | "blue" | "neutral";
    }[]
  >([]);

  const overrideMut = useMutation({
    mutationFn: (action: OverrideAction) =>
      overrideJunction(junctionId, action, reason.trim()),
    onSuccess: (result: OverrideResult) => {
      setActionError(null);
      setReasonError(null);
      setReason("");
      // Truthful result rendering (contract §6): action + message + command
      // identity + delivery status. PENDING delivery = published, awaiting the
      // device acknowledgement — NOT a confirmed signal change.
      const delivery = result.delivery?.status ?? result.command?.status ?? "";
      const tone: "green" | "red" | "blue" | "neutral" =
        delivery === "ACKNOWLEDGED"
          ? "green"
          : delivery === "PUBLISH_FAILED"
            ? "red"
            : "blue";
      setActionLog((prev) =>
        [
          {
            title: `${result.action} — ${result.message || result.command?.type || "no command issued"}`,
            meta:
              result.command
                ? `attempt ${result.command.attempt} · ${result.command.status} · correlation ${result.command.correlation_id}`
                : "no command was issued for this action",
            delivery: result.delivery?.status ?? null,
            release: result.release
              ? `Release published (attempt ${result.release.attempt}) — pending until the device acknowledges.`
              : null,
            tone,
          },
          ...prev,
        ].slice(0, 8),
      );
      void queryClient.invalidateQueries({ queryKey: ["live"] });
      void queryClient.invalidateQueries({ queryKey: ["commands"] });
    },
    onError: (err) => {
      setActionError(
        err instanceof ApiError
          ? err.code !== "REQUEST_FAILED" && err.code !== "UNKNOWN"
            ? `${err.code} — ${err.message}`
            : err.message
          : "Override failed — please try again.",
      );
    },
  });

  const runOverride = (action: OverrideAction) => {
    setActionError(null);
    setReasonError(null);
    if (junctionId === "") return;
    if (reason.trim().length < 5) {
      setReasonError("A reason is required (min 5 characters) and is audit-logged.");
      return;
    }
    overrideMut.mutate(action);
  };

  const selectJunction = (value: string) => {
    setActionLog([]);
    setActionError(null);
    setReasonError(null);
    setSearchParams({ junction: value }, { replace: true });
  };

  const center: [number, number] =
    junction && junction.latitude !== null && junction.longitude !== null
      ? [junction.latitude, junction.longitude]
      : DEFAULT_CENTER;

  return (
    <div className="page-body">
      <PageHeader
        title="My Junctions"
        subtitle={item?.subtitle ?? "Junctions assigned to you and their live state"}
      />

      {junctions.error && (
        <InlineError error={junctions.error} fallback="Could not load your junctions." />
      )}

      {junctions.isLoading ? (
        <Loading label="Loading junctions" />
      ) : mine.length === 0 ? (
        <Empty
          icon="traffic"
          title="No junctions assigned"
          body="Ask an administrator to assign you to junctions — the live view and manual override appear here."
        />
      ) : (
        <>
          <div style={{ maxWidth: 360 }}>
            <SelectField
              label="Junction"
              value={junction?.id ?? ""}
              onChange={selectJunction}
              options={mine.map((j) => ({ value: j.id, label: j.name }))}
            />
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 10,
              flexWrap: "wrap",
            }}
          >
            {live.data && (
              <Txt muted>observed {fmtRelative(live.data.observed_at)}</Txt>
            )}
            <FreshnessCaption updatedAt={live.dataUpdatedAt} />
          </div>
          <StaleBanner stale={stale} />
          {live.error && (
            <InlineError
              error={live.error}
              fallback="Could not refresh live sessions — showing the last loaded data."
            />
          )}

          {junction === null ? null : (
            <>
              {junctionState && (
                <Card
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    flexWrap: "wrap",
                  }}
                >
                  <Txt style={{ fontWeight: 700 }}>{junction.name}</Txt>
                  <Badge
                    label={junctionState.online ? "DEVICE ONLINE" : "DEVICE OFFLINE"}
                    tone={junctionState.online ? "green" : "red"}
                  />
                  <Txt muted style={{ fontSize: 12 }}>
                    last seen {fmtRelative(junctionState.last_seen_at)}
                  </Txt>
                  {/* Contract §5: telemetry without a state key → "Unknown". */}
                  <Badge
                    label={junctionState.state ?? "Unknown"}
                    tone={
                      junctionState.state
                        ? statusBadgeTone(junctionState.state)
                        : "neutral"
                    }
                  />
                </Card>
              )}
              <MapView
                ariaLabel={`Live map of ${junction.name}`}
                dots={dots}
                center={center}
                zoom={15}
                height={400}
              />

              <SectionTitle>Current Commands</SectionTitle>
              {junctionCommands.length === 0 ? (
                <Txt muted>No active commands at {junction.name}.</Txt>
              ) : (
                <Card>
                  <Timeline
                    items={junctionCommands.map((command) => ({
                      title: `${command.type}${command.approach ? ` · ${command.approach}` : ""}`,
                      meta: command.status,
                      tone: timelineTone(command.status),
                    }))}
                  />
                </Card>
              )}

              <SectionTitle>Manual Override</SectionTitle>
              <Card style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <Txt muted>
                  Overrides are audit-logged with your identity and rate-limited.
                </Txt>
                <Field
                  label="Reason"
                  icon="notes"
                  placeholder="Why is this override needed? (min 5 characters)"
                  value={reason}
                  error={reasonError ?? undefined}
                  onChange={(e) => {
                    setReason(e.target.value);
                    if (reasonError) setReasonError(null);
                  }}
                />
                <div style={{ display: "flex", gap: 9, flexWrap: "wrap" }}>
                  {OVERRIDES.map((override) => (
                    <Button
                      key={override.action}
                      title={override.title}
                      tone={override.tone}
                      loading={overrideMut.isPending && overrideMut.variables === override.action}
                      disabled={overrideMut.isPending}
                      onClick={() => runOverride(override.action)}
                    />
                  ))}
                </div>
                {actionError && <InlineError error={actionError} />}
                {actionLog.length > 0 && (
                  <Timeline
                    items={actionLog.map((entry) => ({
                      title: entry.title,
                      meta:
                        entry.meta +
                        (entry.delivery
                          ? ` · delivery ${entry.delivery.toLowerCase()}`
                          : "") +
                        (entry.release ? ` · ${entry.release}` : ""),
                      tone: entry.tone,
                    }))}
                  />
                )}
                <Txt muted>
                  Acknowledged means the junction device received the command —
                  it does not confirm the signal itself changed.
                </Txt>
              </Card>

              <SectionTitle>Telemetry</SectionTitle>
              {telemetry.isLoading ? (
                <Loading label="Loading telemetry" />
              ) : telemetry.error ? (
                <InlineError error={telemetry.error} fallback="Could not load telemetry." />
              ) : (telemetry.data?.items ?? []).length === 0 ? (
                <Txt muted>No telemetry received yet.</Txt>
              ) : (
                <Card style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {(telemetry.data?.items ?? []).map((row, i) => (
                    <div key={`${row.at}-${i}`} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <Txt muted style={{ fontSize: 12 }}>
                        {fmtDateTime(row.at)} · {fmtRelative(row.at)}
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
                    </div>
                  ))}
                </Card>
              )}

              <SectionTitle>Detections</SectionTitle>
              {detections.isLoading ? (
                <Loading label="Loading detections" />
              ) : detections.error ? (
                <InlineError error={detections.error} fallback="Could not load detections." />
              ) : (detections.data ?? []).length === 0 ? (
                <Txt muted>No vehicle detections recorded yet.</Txt>
              ) : (
                <Table
                  rows={detections.data ?? []}
                  keyOf={(d) => d.id}
                  columns={[
                    {
                      key: "detected_at",
                      header: "Detected at",
                      render: (d) => fmtDateTime(d.detected_at),
                    },
                    { key: "class_name", header: "Class" },
                    {
                      key: "confidence",
                      header: "Confidence",
                      align: "right",
                      render: (d) =>
                        d.confidence <= 1
                          ? `${Math.round(d.confidence * 100)}%`
                          : String(d.confidence),
                    },
                  ]}
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
