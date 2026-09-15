/**
 * UI kit — web mirror of client/components/ui.tsx.
 *
 * Same inventory (Card, Badge, Button, Field, Txt, Icon, Empty, Header,
 * Row, SectionTitle + web counterparts StatCard/Table for the app's rows,
 * Drawer for the app's bottom Sheet) with the same visual language: 16px
 * cards with the soft #668CBD 8% shadow, gradient buttons, pill badges on
 * light token backgrounds, small-bold-label fields.
 *
 * Styles live in src/styles/ui.css (plain CSS on the theme tokens).
 */

import {
  useEffect,
  useId,
  useState,
  type CSSProperties,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import {
  initialsOf,
  type BadgeTone,
} from "@/components/helpers";
import type { AuthUser } from "@/types/api";

export type { BadgeTone } from "@/components/helpers";

// ---- Icon (Material Symbols ligature — web counterpart of the app's MCI) ----

/** Material Symbols ligature name, e.g. "dashboard", "local_hospital". */
export type IconName = string;

export function Icon({
  name,
  size = 24,
  color = "var(--blue)",
  style,
}: {
  name: IconName;
  size?: number;
  color?: string;
  style?: CSSProperties;
}) {
  return (
    <span
      className="ms"
      aria-hidden
      style={{ fontSize: size, color, lineHeight: 1, ...style }}
    >
      {name}
    </span>
  );
}

// ---- Txt ----

export function Txt({
  children,
  muted = false,
  as = "span",
  className,
  style,
}: {
  children?: ReactNode;
  muted?: boolean;
  as?: "span" | "div" | "p" | "h1" | "h2" | "h3";
  className?: string;
  style?: CSSProperties;
}) {
  const Tag = as;
  return (
    <Tag
      className={`txt${muted ? " txt--muted" : ""}${className ? ` ${className}` : ""}`}
      style={style}
    >
      {children}
    </Tag>
  );
}

// ---- Card ----

export function Card({
  children,
  className,
  style,
}: {
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div className={`card${className ? ` ${className}` : ""}`} style={style}>
      {children}
    </div>
  );
}

// ---- Badge ----

export function Badge({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: BadgeTone;
}) {
  return (
    <span className={`badge badge--${tone}`}>
      <span
        className="badge-dot"
        style={{ background: "currentColor" }}
        aria-hidden
      />
      {label}
    </span>
  );
}

// ---- Button ----

export function Button({
  title,
  onClick,
  type = "button",
  tone = "primary",
  loading = false,
  disabled = false,
  icon,
  block = false,
}: {
  title: string;
  onClick?: () => void;
  type?: "button" | "submit";
  tone?: "primary" | "quiet" | "danger";
  loading?: boolean;
  disabled?: boolean;
  icon?: IconName;
  block?: boolean;
}) {
  return (
    <button
      type={type}
      className={`btn btn--${tone}${block ? " btn--block" : ""}`}
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading}
      aria-label={title}
    >
      {loading ? (
        <span className="btn-spinner" aria-hidden />
      ) : (
        <>
          {title}
          {icon && <Icon name={icon} size={22} color="currentColor" />}
        </>
      )}
    </button>
  );
}

// ---- Field (label + input, optional icon / password reveal / error) ----

export interface FieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
  icon?: IconName;
  error?: string;
  password?: boolean;
  type?: "text" | "email" | "password" | "number" | "tel" | "search" | "url";
}

export function Field({
  label,
  icon,
  error,
  password = false,
  type = "text",
  ...props
}: FieldProps) {
  const [visible, setVisible] = useState(false);
  const id = useId();
  const inputType = password && !visible ? "password" : type;
  return (
    <div className="field-wrap">
      <div className={`field${error ? " field--error" : ""}`}>
        {icon && <Icon name={icon} size={22} color="var(--muted)" />}
        <div className="field-body">
          <label className="field-label" htmlFor={id}>
            {label}
          </label>
          <input
            {...props}
            id={id}
            className="field-input"
            type={inputType}
            aria-label={label}
            aria-invalid={error ? true : undefined}
          />
        </div>
        {password && (
          <button
            type="button"
            className="field-eye"
            onClick={() => setVisible((v) => !v)}
            aria-label={visible ? "Hide password" : "Show password"}
          >
            <Icon name={visible ? "visibility_off" : "visibility"} size={20} color="var(--muted)" />
          </button>
        )}
      </div>
      {error && (
        <span className="field-error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

// ---- StatCard ----

export function StatCard({
  label,
  value,
  tone = "blue",
  icon,
}: {
  label: string;
  value: string;
  tone?: BadgeTone | "neutral";
  icon?: IconName;
}) {
  return (
    <Card className="stat">
      {icon && (
        <span className={`stat-icon stat-icon--${tone}`}>
          <Icon name={icon} size={24} color="currentColor" />
        </span>
      )}
      <span>
        <span className="stat-label">{label}</span>
        <span className="stat-value">{value}</span>
      </span>
    </Card>
  );
}

// ---- Table (web counterpart of the app's rows) ----

export interface TableColumn<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
}

export function Table<T>({
  columns,
  rows,
  keyOf,
  emptyFallback,
}: {
  columns: TableColumn<T>[];
  rows: T[];
  keyOf: (row: T) => string;
  emptyFallback?: ReactNode;
}) {
  if (rows.length === 0 && emptyFallback) {
    return <>{emptyFallback}</>;
  }
  return (
    <Card className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.align === "right" ? "table-col--right" : undefined}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={keyOf(row)}>
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={c.align === "right" ? "table-col--right" : undefined}
                >
                  {c.render
                    ? c.render(row)
                    : String(
                        (row as unknown as Record<string, unknown>)[c.key] ?? "",
                      )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

// ---- Timeline (vertical dots, like the app's History) ----

export interface TimelineItem {
  title: string;
  meta?: string;
  tone?: "green" | "red" | "blue" | "neutral";
}

export function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <div className="timeline">
      {items.map((item, i) => (
        <div className="timeline-row" key={`${item.title}-${i}`}>
          <div className="timeline-rail">
            <span className={`timeline-dot timeline-dot--${item.tone ?? "blue"}`} />
            {i < items.length - 1 && <span className="timeline-line" />}
          </div>
          <div>
            <Txt>{item.title}</Txt>
            {item.meta && <Txt muted className="timeline-meta">{item.meta}</Txt>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---- Drawer (right slide-over — web counterpart of the app's Sheet) ----

export function Drawer({
  open,
  title,
  onClose,
  children,
  width = 460,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children?: ReactNode;
  width?: number;
}) {
  // Close on Escape, like the app's onRequestClose.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <div className={`drawer-root${open ? " drawer-root--open" : ""}`} aria-hidden={!open}>
      <div className="drawer-backdrop" onClick={onClose} aria-label="Close dialog" />
      <aside className="drawer" style={{ width }} role="dialog" aria-label={title}>
        <div className="drawer-head">
          <span className="drawer-title">{title}</span>
          <button type="button" className="drawer-close" onClick={onClose} aria-label="Close dialog">
            <Icon name="close" size={24} color="var(--navy)" />
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}

// ---- Empty ----

export function Empty({
  title,
  body,
  icon = "event_note",
}: {
  title: string;
  body: string;
  icon?: IconName;
}) {
  return (
    <Card className="empty">
      <Icon name={icon} size={42} />
      <Txt as="div" className="empty-title">{title}</Txt>
      <Txt muted className="empty-body">{body}</Txt>
    </Card>
  );
}

// ---- Row / SectionTitle ----

export function Row({
  children,
  className,
  style,
}: {
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div className={`row${className ? ` ${className}` : ""}`} style={style}>
      {children}
    </div>
  );
}

export function SectionTitle({
  children,
  action,
}: {
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="section-title">
      <Txt as="span" className="section-title-text">{children}</Txt>
      {action}
    </div>
  );
}

// ---- PageHeader (page-level title + subtitle, like the app Header) ----

export function PageHeader({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div style={{ flex: 1, minWidth: 0 }}>
        <Txt as="h1" className="page-head-title">{title}</Txt>
        <Txt as="p" muted className="page-head-subtitle">{subtitle}</Txt>
      </div>
      {children && <Row>{children}</Row>}
    </div>
  );
}

// ---- Avatar (initials circle; initials via helpers.initialsOf) ----

export function Avatar({
  name,
  size = "md",
  onDark = false,
}: {
  name: string;
  size?: "sm" | "md";
  onDark?: boolean;
}) {
  return (
    <span
      className={`avatar${size === "sm" ? " avatar--sm" : ""}${onDark ? " avatar--on-dark" : ""}`}
      aria-hidden
    >
      {initialsOf(name)}
    </span>
  );
}

// ---- Header (portal top bar: page title + role chip + initials avatar) ----

const ROLE_CHIP: Record<string, BadgeTone> = {
  admin: "purple",
  hospital: "green",
  police: "blue",
};

export function Header({
  title,
  user,
  children,
}: {
  title: string;
  user: AuthUser;
  children?: ReactNode;
}) {
  return (
    <header className="topbar">
      <Txt as="h1" className="page-head-title">{title}</Txt>
      <div className="topbar-right">
        {children}
        <Badge label={user.role} tone={ROLE_CHIP[user.role.trim().toLowerCase()] ?? "neutral"} />
        <Avatar name={user.name ?? user.email} />
      </div>
    </header>
  );
}
