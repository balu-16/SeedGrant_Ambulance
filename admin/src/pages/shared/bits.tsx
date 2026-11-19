/**
 * Small shared pieces for the HOSPITAL / POLICE pages that the ui kit does
 * not cover: inline loading card, inline error banner (never alert()), a
 * label-over-select field styled like the kit's Field, and the freshness
 * pieces (Last-updated caption, stale banner, Stale GPS badge) shared by all
 * three live views. Freshness logic lives in shared/freshness.ts.
 */

import { useId } from "react";
import { ApiError } from "@/services/api";
import { Badge, Card, Icon, Txt } from "@/components/ui";
import { isGpsStale, useFreshness } from "@/pages/shared/freshness";

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status">
      <Card className="empty">
        <span className="spinner" aria-hidden />
        <Txt muted>{label}…</Txt>
      </Card>
    </div>
  );
}

export function InlineError({
  error,
  fallback = "Something went wrong — please try again.",
}: {
  error: unknown;
  fallback?: string;
}) {
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : typeof error === "string" && error
          ? error
          : fallback;
  return (
    <div className="login-error" role="alert">
      <Icon name="error" size={18} color="var(--red)" />
      <span>{message}</span>
    </div>
  );
}

export interface SelectOption {
  value: string;
  label: string;
}

export function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
}) {
  const id = useId();
  return (
    <div className="field">
      <div className="field-body">
        <label className="field-label" htmlFor={id}>
          {label}
        </label>
        <select
          id={id}
          className="field-input"
          value={value}
          aria-label={label}
          onChange={(e) => onChange(e.target.value)}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

// ---- Freshness (contract §9: show data age; stale after portal_stale_seconds) ----

/** "Last updated Xs ago" caption (null age → "Last updated —"). */
export function FreshnessCaption({
  updatedAt,
}: {
  updatedAt: number | undefined;
}) {
  const { secondsAgo } = useFreshness(updatedAt);
  return (
    <Txt muted style={{ fontSize: 12 }}>
      Last updated{" "}
      {secondsAgo === null
        ? "—"
        : secondsAgo < 5
          ? "just now"
          : `${secondsAgo}s ago`}
    </Txt>
  );
}

/** Banner shown when the last successful refresh exceeds the portal threshold. */
export function StaleBanner({ stale }: { stale: boolean }) {
  if (!stale) return null;
  return (
    <div className="stale-banner" role="status">
      <Icon name="hourglass_empty" size={18} color="var(--muted)" />
      <span>
        Data may be out of date — the last refresh did not complete. Retrying
        every 10 seconds.
      </span>
    </div>
  );
}

/** "Stale GPS" pill when the latest fix is older than the GPS threshold. */
export function GpsStaleBadge({
  recordedAt,
  gpsStaleSeconds,
}: {
  recordedAt: string | null | undefined;
  gpsStaleSeconds: number;
}) {
  if (!isGpsStale(recordedAt, gpsStaleSeconds)) return null;
  return <Badge label="Stale GPS" tone="neutral" />;
}
