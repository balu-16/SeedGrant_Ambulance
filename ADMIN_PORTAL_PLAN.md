# Admin Portal — Detailed Plan

Web-based control portal for the SeedGrant emergency-priority system. Three personas:
**ADMIN** (full control over everything), **HOSPITAL** (hospital owners, fleet-scoped),
**POLICE** (junction traffic authority, junction-scoped).

---

## 1. Location & stack (where in the codebase)

**New top-level folder `admin/`** — a sibling of `client/` and `server/`:

```
SeedGrant_Asrith/
├── server/        # FastAPI backend (adds portal APIs + roles)
├── client/        # Expo driver app (unchanged)
├── admin/         # ← NEW: web admin portal (Vite + React + TS)
│   ├── src/
│   │   ├── app/            # router + layout (shell, sidebar, guards)
│   │   ├── pages/          # one folder per page (mirrors client/features/)
│   │   ├── components/     # ui kit mirroring client/components/ui.tsx
│   │   ├── services/       # api client (mirrors client/services/api.ts)
│   │   ├── types/          # API models (mirrors client/types/)
│   │   └── styles/         # theme.css (tokens copied from client/constants/theme.ts)
│   ├── index.html
│   ├── vite.config.ts      # dev proxy → http://localhost:8000
│   └── package.json
```

**Why here and not inside `client/` or `server/`:**
- `client/` is React Native/Expo — a web SPA has a different toolchain; mixing them breaks Expo's config.
- `server/` stays API-only (clean separation). The **built** portal (`admin/dist`) is mounted
  into FastAPI as static files at `/admin` in production — one deployment, one origin (no CORS
  issues; the existing rate-limiting / request-ID middleware covers portal traffic).

**Stack:** Vite + React 19 + TypeScript (strict) · TanStack Query (API state/polling) ·
react-leaflet + OpenStreetMap tiles (free live map, no API key) · plain CSS with custom
properties (tokens copied verbatim from the app — see §3) · Material Symbols icons
(web equivalent of the app's MaterialCommunityIcons).

**Auth:** same JWT flow as the driver app — `POST /auth/login` → access+refresh tokens in
memory + storage; single-flight refresh on 401 (reuse the logic already proven in
`client/services/api.ts`). Roles come from the token and are re-verified server-side on
every request.

---

## 2. Roles & access model (backend changes)

Today `users.role` is `"ADMIN" | "DRIVER"` (`server/app/models/user.py`) and
`require_role(*roles)` is already generic (`server/app/core/dependencies.py`).

| Change | Detail |
|---|---|
| New roles | `users.role` gains `HOSPITAL` and `POLICE` (String(16) fits). Public `/auth/register` stays **DRIVER-only** (fixed in the hardening pass). Portal users are created by ADMIN only. |
| Scope: hospital | New `hospitals` table; `users.hospital_id` FK (nullable); `ambulances.hospital_id` FK (nullable). A HOSPITAL user sees only their hospital's fleet/data. |
| Scope: police | New `police_assignments` table (`user_id` ↔ `junction_id`). A POLICE user sees/controls only their assigned junctions. |
| Scope enforcement | Server-side on every query (never trust the client). `require_role` extended with `require_any(...)` helpers. |
| Migration | `0005_admin_portal.py`: hospitals table + FKs + police_assignments + indexes. |

---

## 3. UI similarity with the app

Copy the exact design tokens from `client/constants/theme.ts` into `admin/src/styles/theme.css`:

| Token | Value | Portal use |
|---|---|---|
| blue | `#1475FF` | primary buttons, active nav, links |
| navy / heading | `#10214C` / `#192F64` | sidebar bg, headings |
| pale | `#F3F8FF` | page background |
| blueLight | `#EAF3FF` | hover/selected rows, chips |
| green / greenLight | `#009B51` / `#E3FAF0` | "granted/online/completed" badges |
| purple / purpleLight | `#7453DA` / `#F0EBFF` | "priority requested" badges |
| red / redLight | `#F52F3C` / `#FFF0F2` | "emergency active/offline/expired" badges |
| muted / border | `#6B7F9F` / `#E2EBF8` | secondary text, table borders |
| shadow | `#668CBD` 8% / r10 | card elevation (same soft look) |

**Component kit (`admin/src/components/`) mirrors `client/components/ui.tsx` 1:1:**
`Card` (16px radius, soft shadow) · `Badge` (same status→color mapping: granted=green,
requested=purple, released/ready=neutral, active emergency=red) · `Button` · `Field` (inputs)
· `StatCard` · `Table` (web counterpart of the app's rows) · `Timeline` (reuse the app's
History event-timeline concept for emergency detail) · `Drawer` (web counterpart of the
app's bottom `Sheet`) · `Empty` · `Header` with role chip.

**Layout:** desktop-first — left navy sidebar (Dashboard / Live Map / Emergencies /
role section / Settings), top header with role badge and user avatar; responsive collapse
to a bottom tab bar on tablets, like the app's tabs.

---

## 4. Pages & features per persona

### 4.1 ADMIN — full control (sees and does everything)

| Page | Features |
|---|---|
| **Dashboard** | System KPIs: active emergencies, fleet size, devices online, commands pending; recent activity feed; quick links. |
| **Live Map** | All active emergency sessions on a map (latest GPS), junction markers colored by state, click → session detail drawer (timeline, events, driver, ambulance, priority state). |
| **Emergencies** | Full history table (all drivers/hospitals), filters (status, date range, junction, ambulance), detail drawer with event timeline; CSV export. |
| **Users** | Create/disable/enable portal users (ADMIN/HOSPITAL/POLICE/DRIVER), reset passwords, assign hospital or junctions, see last-login; audit-logged. |
| **Hospitals** | CRUD hospitals (name, address, geocode, contact); assign/unassign ambulances and hospital users. |
| **Junctions** | CRUD junctions + 4 approaches (directions, heading windows, radius, entry coords) — supersedes seed-only setup; per-junction stats. |
| **Devices** | Register Pi devices, rotate API keys (key shown once), online/offline status, last heartbeat, telemetry browser per device. |
| **Fleet** | All ambulances: register/edit, assign driver, assign hospital, on-duty toggle. |
| **Analytics** | Avg emergency duration, junction crossing times, commands by status, per-junction heatmap, peak hours, timeouts — date-range filter. |
| **Audit Log** | Every audited action (logins, overrides, key rotations, reassignments) with actor/filters. |
| **System** | `POST /admin/sweep` (force), `/admin/config-check` view, data-retention settings, MQTT health. |

### 4.2 HOSPITAL (hospital owner) — fleet-scoped, read + manage own fleet

Scope: only ambulances, drivers, and emergencies belonging to their `hospital_id`.

| Page | Features |
|---|---|
| **Dashboard** | Their fleet at a glance: ambulances on-duty vs in-emergency vs idle; drivers on shift; their active emergencies; today's completed trips. |
| **Live Tracking** | Map + list of **their** active emergencies: live position, speed, elapsed time, current junction/priority state; auto-refresh (10s). |
| **My Fleet** | Register/edit their ambulances (vehicle no, base hospital, on-duty); assign/reassign drivers from their hospital's driver list; device pairing status per ambulance. |
| **Drivers** | Drivers linked to the hospital (self-registered DRIVER accounts, linked by the owner), activity summary, last emergency per driver. |
| **Emergencies** | History of their fleet only: filters, duration/junction stats, event timeline drawer, **CSV export** for records/insurance. |
| **Alerts** | Notifications when a fleet ambulance starts/ends an emergency, times out, or its device goes offline (in-app toasts + alert feed). |
| **Settings** | Hospital profile (name/address/contact), password change, notification preferences. |

**Not available to HOSPITAL:** junction control, overrides, device keys, user management,
other hospitals' data, telemetry/detections.

### 4.3 POLICE (junction traffic authority) — junction-scoped, monitor + override

Scope: only their assigned junctions (`police_assignments`). Focus: what's happening at
*their* intersections and manual control when automation isn't enough.

| Page | Features |
|---|---|
| **Dashboard** | Their junctions as cards: current state (idle / priority requested / crossing), which ambulance + approach, device online badge, commands pending; one tap → junction detail. |
| **Junction Detail / Live** | Live map of the junction + approaching ambulance; current command status timeline (PENDING → SENT → ACKNOWLEDGED → RELEASED / EXPIRED); latest detections (vehicle counts per approach from YOLO); telemetry stream (last N readings). |
| **Manual Override** | **Force release** priority (issues RELEASE_PRIORITY immediately), **hold/cancel** an active priority, **re-issue** an expired/unacked command — each with a required reason, audit-logged with officer identity, rate-limited; ADMIN sees all overrides in the audit log. |
| **Command Log** | Every command for their junctions: filter by type/status/date; shows correlation id, issued/expiry, acked-by, retry count. |
| **Device Health** | Their junction's Pi: online/offline, last heartbeat, telemetry history chart; offline/expired-ack alerts. |
| **Analytics** | Per-junction: emergencies served, avg crossing duration, override frequency, peak hours, detection counts per approach. |
| **Settings** | Password change; notification preferences (device offline, command expired). |

**Not available to POLICE:** fleet/hospital data, user management, junction geometry edits
(view-only), device key rotation, other officers' junctions.

### 4.4 Shared

- Login page styled like the app (`reference/LoginPage.png`: illustration panel + form card).
- Role-aware navigation (sidebar items render per role; deep links re-checked server-side).
- Alert feed + toast notifications; empty states like the app's `Empty` component.
- All list pages: search + filters + pagination (server-side, consistent with the API).

---

## 5. New/extended backend endpoints

| Endpoint | Method(s) | Roles | Notes |
|---|---|---|---|
| `/admin/users` | GET/POST/PATCH | ADMIN | portal user CRUD, scope assignment, disable |
| `/admin/hospitals` (+`/{id}`) | GET/POST/PATCH | ADMIN (write), HOSPITAL (read own) | hospital CRUD |
| `/ambulances` | GET (scoped), POST, PATCH | ADMIN all; HOSPITAL own | hospital_id added |
| `/admin/live` | GET | ADMIN/HOSPITAL/POLICE (scoped) | active sessions + last GPS + junction state; 10s polling (SSE upgrade path) |
| `/admin/alerts` | GET | all portal roles (scoped) | derived alerts feed |
| `/admin/analytics/overview` | GET | all portal roles (scoped) | aggregates w/ date filters |
| `/admin/audit` | GET | ADMIN (all), POLICE (own actions) | audit log viewer |
| `/junctions/{id}/override` | POST | POLICE (assigned), ADMIN | FORCE_RELEASE / HOLD / REISSUE + reason; audit-logged |
| `/commands/admin/list` | GET (extended) | ADMIN, POLICE (scoped) | filters: junction/status/date |
| `/junctions` CRUD | extended | ADMIN | approaches managed here |
| `/vision/detections` | GET (extended) | + POLICE (scoped by junction) | detection history |

---

## 6. Phases (each independently verifiable)

| Phase | Content | Verification |
|---|---|---|
| **0 — Backend foundation** | Migration 0005 (hospitals, police_assignments, FKs), role extensions, scoped require helpers, `/admin/users` + `/admin/hospitals` + scoped `/ambulances` | pytest (new endpoint tests in the existing suite), manual API smoke |
| **1 — Portal scaffold** | `admin/` Vite app, theme.css from app tokens, ui kit, login page, guarded layout, api client w/ refresh | login as each role → correct nav renders |
| **2 — ADMIN core** | Dashboard, Live Map, Emergencies + detail drawer, Users, Junctions, Devices, Fleet, Analytics, Audit | full admin walkthrough vs seeded data |
| **3 — HOSPITAL role** | fleet/driver management + scoped live/history/alerts/exports | two hospitals seeded → zero cross-leak |
| **4 — POLICE role** | junction dashboard, command log, device health, **manual override** (+audit) | override issues a real command visible in `commands/admin/list` and to a Pi |
| **5 — Realtime & polish** | SSE for live map/alerts, CSV exports, responsive pass, e2e (Playwright) against portal | e2e suite green |

**Deployment:** `admin/` builds to static files; FastAPI mounts `admin/dist` at `/admin`
(`StaticFiles(html=True)`), so production is a single origin.

---

## 7. Security notes

- No public self-signup for portal roles — ADMIN creates users; passwords via one-time
  reset link or admin-set + forced change.
- Scoping enforced in SQL (`WHERE hospital_id = …` / `junction_id IN …`), never in the UI.
- Every override, user change, key rotation is audit-logged with actor.
- Overrides are rate-limited (middleware already exists) and require a reason string.
- Tokens: same JWT machinery; portal sessions get shorter access TTL (e.g. 15 min) — config change only.
