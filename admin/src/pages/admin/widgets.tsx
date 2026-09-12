/**
 * ADMIN pages — small shared UI pieces built on the portal kit
 * (components/ui): inline error/loading states, compact row buttons,
 * select/checkbox fields, the CSS-only bar list for Analytics and the
 * key/value definition list used by drawers and the System page.
 */

import { useId, type ReactNode } from "react";
import type { BadgeTone } from "@/components/helpers";
import { Card, Icon, Txt } from "@/components/ui";
import { errMsg } from "@/pages/admin/shared";

/** Inline error Card — admin pages render every failure here (never alert()). */
export function ErrorCard({
  title = "Something went wrong",
  error,
  onRetry,
}: {
  title?: string;
  error: unknown;
  onRetry?: () => void;
}) {
  return (
    <Card className="admin-error">
      <Icon name="error" size={22} color="var(--red)" />
      <span style={{ flex: 1, minWidth: 0 }}>
        <Txt as="div" style={{ fontWeight: 600 }}>
          {title}
        </Txt>
        <Txt muted>{errMsg(error)}</Txt>
      </span>
      {onRetry && <MiniButton title="Retry" onClick={onRetry} />}
    </Card>
  );
}

/** Compact quiet/danger button for table rows and toolbars (kit btn is 52px). */
export function MiniButton({
  title,
  onClick,
  tone = "quiet",
  disabled = false,
  loading = false,
  icon,
}: {
  title: string;
  onClick?: () => void;
  tone?: "primary" | "quiet" | "danger";
  disabled?: boolean;
  loading?: boolean;
  icon?: string;
}) {
  return (
    <button
      type="button"
      className={`btn btn--${tone}`}
      style={{
        minHeight: 34,
        padding: "7px 13px",
        fontSize: 13,
        lineHeight: "18px",
        gap: 7,
        borderRadius: 11,
        boxShadow: tone === "quiet" ? "none" : undefined,
      }}
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading}
      aria-label={title}
    >
      {loading ? (
        <span
          className="btn-spinner"
          style={{ width: 14, height: 14, borderWidth: 2 }}
          aria-hidden
        />
      ) : (
        <>
          {title}
          {icon && <Icon name={icon} size={17} color="currentColor" />}
        </>
      )}
    </button>
  );
}

/** Subtle centered spinner (theme.css .spinner) for page/section loading. */
export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div className="admin-loading" role="status" aria-label={label}>
      <span className="spinner" />
    </div>
  );
}

/** Labelled select styled like the kit's Field. */
export function SelectField({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className="field-wrap">
      <div className="field">
        <div className="field-body">
          <label className="field-label" htmlFor={id}>
            {label}
          </label>
          <select
            id={id}
            className="admin-select"
            value={value}
            onChange={(e) => onChange(e.target.value)}
          >
            {children}
          </select>
        </div>
      </div>
    </div>
  );
}

/** Checkbox row used for junction multi-assign and on-duty toggles. */
export function CheckRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="admin-check">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>{label}</span>
    </label>
  );
}

/** CSS-only horizontal bar list (Analytics — no chart library). */
export function BarList({
  rows,
  emptyText = "No data in this range.",
}: {
  rows: { label: string; value: number; tone?: BadgeTone }[];
  emptyText?: string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (rows.length === 0) return <Txt muted>{emptyText}</Txt>;
  return (
    <div className="admin-bars">
      {rows.map((r) => (
        <div className="admin-bar" key={r.label}>
          <span className="admin-bar-label" title={r.label}>
            {r.label}
          </span>
          <span className="admin-bar-track">
            <span
              className={`admin-bar-fill admin-bar-fill--${r.tone ?? "blue"}`}
              style={{
                width: `${Math.max(2, Math.round((r.value / max) * 100))}%`,
              }}
            />
          </span>
          <span className="admin-bar-value">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

/** Key/value definition list (drawer details, config-check, sweep result). */
export function KVList({ entries }: { entries: [string, string][] }) {
  return (
    <dl className="admin-kv">
      {entries.map(([k, v], i) => (
        <div className="admin-kv-row" key={`${k}-${i}`}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}
