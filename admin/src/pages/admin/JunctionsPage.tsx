/**
 * ADMIN Junctions (plan §4.1) — junction registry table; the detail drawer
 * shows the junction's approaches (direction + heading windows) and a manual
 * override console (FORCE_RELEASE / HOLD / REISSUE, reason required ≥5 chars)
 * via overrideJunction, with results appended to an in-drawer Timeline.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createJunction, deleteJunction, getJunction, listJunctions, overrideJunction, patchJunction } from "@/services/portal";
import type { JunctionSummary, OverrideResult } from "@/types/portal";
import { Badge, Card, Drawer, Empty, Field, PageHeader, Table, Txt, type TableColumn } from "@/components/ui";
import { errMsg, shortId, timelineTone } from "@/pages/admin/shared";
import {
  ErrorCard,
  KVList,
  LoadingBlock,
  MiniButton,
} from "@/pages/admin/widgets";
import "@/pages/admin/admin.css";

type OverrideAction = "FORCE_RELEASE" | "HOLD" | "REISSUE";

export function JunctionsPage() {
  const junctions = useQuery({
    queryKey: ["admin", "junctions"],
    queryFn: listJunctions,
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const items = junctions.data ?? [];
  const selected = items.find((j) => j.id === selectedId) ?? null;

  const onRowSelect = (row: (typeof items)[number]) => setSelectedId(row.id);

  const columns: TableColumn<JunctionSummary>[] = [
    {
      key: "name",
      header: "Junction",
      render: (j) => <Txt style={{ fontWeight: 600 }}>{j.name}</Txt>,
    },
    {
      key: "coords",
      header: "Coordinates",
      render: (j) => (
        <Txt muted className="admin-mono">
          {j.latitude != null && j.longitude != null
            ? `${j.latitude.toFixed(5)}, ${j.longitude.toFixed(5)}`
            : "—"}
        </Txt>
      ),
    },
    {
      key: "id",
      header: "ID",
      render: (j) => (
        <Txt muted className="admin-mono">
          {shortId(j.id)}
        </Txt>
      ),
    },
    {
      key: "radius",
      header: "Radius",
      render: (j) => `${j.radius_m ?? 500}m`,
    },
    {
      key: "status",
      header: "Status",
      render: (j) => (
        <Badge
          label={j.is_active === false ? "INACTIVE" : "ACTIVE"}
          tone={j.is_active === false ? "red" : "green"}
        />
      ),
    },
  ];

  return (
    <div className="page-body">
      <PageHeader
        title="Junctions"
        subtitle="Junctions, approaches and signal configuration"
      />
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <MiniButton title="New junction" onClick={() => setCreateOpen(true)} />
      </div>

      {junctions.isError ? (
        <ErrorCard
          title="Could not load junctions"
          error={junctions.error}
          onRetry={() => void junctions.refetch()}
        />
      ) : junctions.isLoading ? (
        <LoadingBlock label="Loading junctions" />
      ) : (
        <div>
          <Table
            columns={columns}
            rows={items}
            keyOf={(j) => j.id}
            onRowClick={onRowSelect}
            emptyFallback={
              <Empty
                icon="traffic"
                title="No junctions yet"
                body="Junctions and their approaches are seeded by the backend; open one to inspect and override it."
              />
            }
          />
        </div>
      )}

      <Drawer
        open={selected !== null}
        title={selected?.name ?? "Junction"}
        onClose={() => setSelectedId(null)}
        width={480}
      >
        {selected && <JunctionConsole key={selected.id} junction={selected} />}
      </Drawer>
      <Drawer
        open={createOpen}
        title="New junction"
        onClose={() => setCreateOpen(false)}
        width={420}
      >
        <CreateJunctionForm onDone={() => setCreateOpen(false)} />
      </Drawer>
    </div>
  );
}

function CreateJunctionForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () =>
      createJunction({
        name: name.trim(),
        latitude: Number(lat),
        longitude: Number(lon),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin", "junctions"] });
      onDone();
    },
    onError: (e) => setErr(errMsg(e)),
  });
  const valid =
    name.trim().length > 1 &&
    Number.isFinite(Number(lat)) &&
    Number.isFinite(Number(lon)) &&
    Math.abs(Number(lat)) <= 90 &&
    Math.abs(Number(lon)) <= 180;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <Field label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Benz Circle" />
      <Field label="Latitude" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="16.5058" />
      <Field label="Longitude" value={lon} onChange={(e) => setLon(e.target.value)} placeholder="80.6520" />
      <Txt muted>Creates the junction plus 4 standard approaches (auto).</Txt>
      {err && <ErrorCard title="Could not create junction" error={err} onRetry={() => setErr(null)} />}
      <MiniButton title="Create" disabled={!valid || m.isPending} onClick={() => m.mutate()} />
    </div>
  );
}

function JunctionConsole({ junction }: { junction: JunctionSummary }) {
  const detail = useQuery({
    queryKey: ["admin", "junction", junction.id],
    queryFn: () => getJunction(junction.id),
  });

  const [reason, setReason] = useState("");
  const [reasonErr, setReasonErr] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [log, setLog] = useState<OverrideResult[]>([]);

  const m = useMutation({
    mutationFn: (action: OverrideAction) =>
      overrideJunction(junction.id, action, reason.trim()),
    onSuccess: (res) => setLog((prev) => [res, ...prev]),
    onError: (e) => setErr(errMsg(e)),
  });

  function send(action: OverrideAction) {
    if (reason.trim().length < 5) {
      setReasonErr(
        "A reason of at least 5 characters is required — it is written to the audit log.",
      );
      return;
    }
    setReasonErr(null);
    setErr(null);
    m.mutate(action);
  }

  return (
    <>
      <JunctionEditForm junction={junction} />
      <Card>
        <Txt as="div" style={{ fontWeight: 600, marginBottom: 8 }}>
          Approaches
        </Txt>
        {detail.isLoading ? (
          <LoadingBlock label="Loading approaches" />
        ) : detail.isError ? (
          <ErrorCard
            title="Could not load approaches"
            error={detail.error}
            onRetry={() => void detail.refetch()}
          />
        ) : (detail.data?.approaches.length ?? 0) === 0 ? (
          <Txt muted>No approaches configured for this junction.</Txt>
        ) : (
          <KVList
            entries={(detail.data?.approaches ?? []).map((a) => [
              a.direction,
              a.heading_min != null && a.heading_max != null
                ? `heading ${a.heading_min}° – ${a.heading_max}°`
                : "any heading",
            ])}
          />
        )}
      </Card>

      <Card>
        <Txt as="div" style={{ fontWeight: 600, marginBottom: 8 }}>
          Manual override
        </Txt>
        <Txt muted style={{ marginBottom: 10 }}>
          Sends a command to this junction's device. Every override is
          audit-logged with your account.
        </Txt>
        <Field
          label="Reason (min 5 characters)"
          icon="edit_note"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          error={reasonErr ?? undefined}
          placeholder="e.g. Ambulance stuck behind a crash on the north arm"
        />
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
            marginTop: 12,
          }}
        >
          <MiniButton
            tone="danger"
            title="FORCE_RELEASE"
            loading={m.isPending && m.variables === "FORCE_RELEASE"}
            onClick={() => send("FORCE_RELEASE")}
          />
          <MiniButton
            title="HOLD"
            loading={m.isPending && m.variables === "HOLD"}
            onClick={() => send("HOLD")}
          />
          <MiniButton
            title="REISSUE"
            loading={m.isPending && m.variables === "REISSUE"}
            onClick={() => send("REISSUE")}
          />
        </div>
        {err && (
          <div className="admin-inline-error" role="alert" style={{ marginTop: 10 }}>
            {err}
          </div>
        )}
      </Card>

      {log.length > 0 && (
        <Card>
          <Txt as="div" style={{ fontWeight: 600, marginBottom: 8 }}>
            Override results
          </Txt>
          <div className="timeline">
            {log.map((r, i) => (
              <div className="timeline-row" key={`${r.command.id}-${i}`}>
                <div className="timeline-rail">
                  <span
                    className={`timeline-dot timeline-dot--${timelineTone(r.command.status)}`}
                  />
                  {i < log.length - 1 && <span className="timeline-line" />}
                </div>
                <div>
                  <Txt>
                    {r.action} — {r.command.type} (
                    {r.command.approach || "all approaches"})
                  </Txt>
                  <Txt muted className="timeline-meta">
                    {r.command.status} · correlation{" "}
                    {shortId(r.command.correlation_id)} · retries{" "}
                    {r.command.retry_count}
                  </Txt>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  );
}

function JunctionEditForm({ junction }: { junction: JunctionSummary }) {
  const qc = useQueryClient();
  const [name, setName] = useState(junction.name);
  const initialRadius = junction.radius_m ?? 500;
  const initialActive = junction.is_active ?? true;
  const [radius, setRadius] = useState(String(initialRadius));
  const [active, setActive] = useState(initialActive);
  const [msg, setMsg] = useState<string | null>(null);
  const patch = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {};
      if (name.trim() && name.trim() !== junction.name) body.name = name.trim();
      if (radius.trim() && Number(radius) !== initialRadius) body.radius_m = Number(radius);
      if (active !== initialActive) body.is_active = active;
      return patchJunction(junction.id, body as never);
    },
    onSuccess: () => {
      setMsg("Saved.");
      void qc.invalidateQueries({ queryKey: ["admin", "junctions"] });
      void qc.invalidateQueries({ queryKey: ["admin", "junction", junction.id] });
    },
    onError: (e) => setMsg(errMsg(e)),
  });
  const del = useMutation({
    mutationFn: () => deleteJunction(junction.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin", "junctions"] });
    },
    onError: (e) => setMsg(errMsg(e)),
  });
  return (
    <Card>
      <Txt as="div" style={{ fontWeight: 600, marginBottom: 8 }}>Edit junction</Txt>
      <Field label="Name" value={name} onChange={(e) => setName(e.target.value)} />
      <Field label="Radius (m, 10–500)" value={radius} onChange={(e) => setRadius(e.target.value)} placeholder="e.g. 300" />
      <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
        <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
        Active
      </label>
      {msg ? <Txt muted>{msg}</Txt> : null}
      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
        <MiniButton title="Save" loading={patch.isPending} onClick={() => patch.mutate()} />
        <MiniButton
          tone="danger"
          title="Delete"
          loading={del.isPending}
          onClick={() => {
            if (confirm(`Delete junction ${junction.name}? Only junctions without history can be deleted.`)) del.mutate();
          }}
        />
      </div>
      <Txt muted>Deactivation releases open priorities and blocks new ones; delete works only for unused junctions.</Txt>
    </Card>
  );
}
