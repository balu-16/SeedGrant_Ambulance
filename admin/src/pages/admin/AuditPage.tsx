/**
 * ADMIN Audit (plan §4.1) — every audited action with actor and a server-side
 * action filter; detail JSON renders one-line collapsed, expandable inline.
 * Limit/offset pagination.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchAudit } from "@/services/portal";
import type { AuditEntry } from "@/types/portal";
import {
  Badge,
  Empty,
  Field,
  PageHeader,
  Table,
  Txt,
  type TableColumn,
} from "@/components/ui";
import { fmtDateTime } from "@/pages/admin/shared";
import { ErrorCard, LoadingBlock, MiniButton } from "@/pages/admin/widgets";
import "@/pages/admin/admin.css";

const LIMIT = 15;

export function AuditPage() {
  const [actionInput, setActionInput] = useState("");
  const [action, setAction] = useState("");
  const [offset, setOffset] = useState(0);

  const q = useQuery({
    queryKey: ["admin", "audit", action, offset],
    queryFn: () =>
      fetchAudit({ limit: LIMIT, offset, action: action || undefined }),
    placeholderData: keepPreviousData,
  });

  const items = q.data?.items ?? [];

  function applyFilter(next: string) {
    setAction(next);
    setOffset(0);
  }

  const columns: TableColumn<AuditEntry>[] = [
    {
      key: "created_at",
      header: "When",
      render: (r) => fmtDateTime(r.created_at),
    },
    { key: "actor", header: "Actor", render: (r) => r.actor },
    {
      key: "action",
      header: "Action",
      render: (r) => <Badge label={r.action} tone="neutral" />,
    },
    {
      key: "entity",
      header: "Entity",
      render: (r) => (
        <Txt muted className="admin-mono">
          {r.entity}
        </Txt>
      ),
    },
    {
      key: "detail",
      header: "Detail",
      render: (r) => (
        <details className="admin-details">
          <summary className="admin-clamp admin-mono">
            {JSON.stringify(r.detail)}
          </summary>
          <pre
            className="admin-mono"
            style={{
              margin: "6px 0 0",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              color: "var(--heading)",
            }}
          >
            {JSON.stringify(r.detail, null, 2)}
          </pre>
        </details>
      ),
    },
  ];

  return (
    <div className="page-body">
      <PageHeader
        title="Audit"
        subtitle="Every audited action with actor and filters"
      />

      <div className="admin-toolbar">
        <Field
          label="Filter by action"
          icon="filter_alt"
          type="search"
          value={actionInput}
          onChange={(e) => setActionInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") applyFilter(e.currentTarget.value.trim());
          }}
          placeholder="e.g. user.create, junction.override"
        />
        <MiniButton
          title="Apply"
          tone="primary"
          onClick={() => applyFilter(actionInput.trim())}
        />
        {action !== "" && (
          <MiniButton
            title="Clear"
            onClick={() => {
              setActionInput("");
              applyFilter("");
            }}
          />
        )}
      </div>

      {q.isError ? (
        <ErrorCard
          title="Could not load the audit log"
          error={q.error}
          onRetry={() => void q.refetch()}
        />
      ) : q.isLoading ? (
        <LoadingBlock label="Loading audit log" />
      ) : (
        <>
          <div className="admin-toolbar">
            <Txt muted style={{ marginLeft: "auto" }}>
              {action !== "" ? `action: ${action} · ` : ""}offset {offset} ·{" "}
              {items.length} rows
            </Txt>
            <MiniButton
              title="Prev"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - LIMIT))}
            />
            <MiniButton
              title="Next"
              disabled={items.length < LIMIT}
              onClick={() => setOffset(offset + LIMIT)}
            />
          </div>

          <Table
            columns={columns}
            rows={items}
            keyOf={(r) => r.id}
            emptyFallback={
              <Empty
                icon="receipt_long"
                title="No audit entries"
                body={
                  action !== ""
                    ? `No entries match the action "${action}".`
                    : "Audited actions (logins, overrides, changes) appear here as they happen."
                }
              />
            }
          />
        </>
      )}
    </div>
  );
}
