/**
 * ADMIN Junctions (plan §4.1) — junction registry table; the detail drawer
 * shows the junction's approaches (direction + heading windows) and a manual
 * override console (FORCE_RELEASE / HOLD / REISSUE, reason required ≥5 chars)
 * via overrideJunction, with results appended to an in-drawer Timeline.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type MouseEvent } from "react";
import { getJunction, listJunctions, overrideJunction } from "@/services/portal";
import type { JunctionSummary, OverrideResult } from "@/types/portal";
import { Card, Drawer, Empty, Field, PageHeader, Table, Txt, type TableColumn } from "@/components/ui";
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
  const items = junctions.data ?? [];
  const selected = items.find((j) => j.id === selectedId) ?? null;

  const onRowClick = (e: MouseEvent<HTMLDivElement>) => {
    const tr = (e.target as HTMLElement).closest("tr");
    if (!tr || tr.rowIndex === 0) return;
    const row = items[tr.rowIndex - 1];
    if (row) setSelectedId(row.id);
  };

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
  ];

  return (
    <div className="page-body">
      <PageHeader
        title="Junctions"
        subtitle="Junctions, approaches and signal configuration"
      />

      {junctions.isError ? (
        <ErrorCard
          title="Could not load junctions"
          error={junctions.error}
          onRetry={() => void junctions.refetch()}
        />
      ) : junctions.isLoading ? (
        <LoadingBlock label="Loading junctions" />
      ) : (
        <div className="admin-row-click" onClick={onRowClick}>
          <Table
            columns={columns}
            rows={items}
            keyOf={(j) => j.id}
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
