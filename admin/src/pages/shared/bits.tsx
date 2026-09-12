/**
 * Small shared pieces for the HOSPITAL / POLICE pages that the ui kit does
 * not cover: inline loading card, inline error banner (never alert()) and a
 * label-over-select field styled like the kit's Field.
 */

import { useId } from "react";
import { ApiError } from "@/services/api";
import { Card, Icon, Txt } from "@/components/ui";

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
