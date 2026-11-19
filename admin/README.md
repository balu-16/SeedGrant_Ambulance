# SeedGrant Admin — web control portal

Desktop-first admin portal for the SeedGrant emergency traffic priority system,
serving three personas — **ADMIN**, **HOSPITAL**, **POLICE** (DRIVER accounts
use the Expo app in `client/`, never this portal). Built in the same visual
language as the driver app: design tokens are copied verbatim from
`client/constants/theme.ts` and the UI kit mirrors `client/components/ui.tsx`.

**Status: complete.** All three persona page sets (ADMIN / HOSPITAL / POLICE)
are implemented and wired to the live backend: live map, emergencies with
server-side filters + timelines + server CSV export, users/hospitals/junctions
management, fleet, device health with telemetry drawers, alerts, analytics,
audit, command log with manual overrides, and settings. Sessions use the
portal-auth contract (memory-only access token + HttpOnly cookie refresh),
freshness (data-age captions, stale banners, "Stale GPS"), truthful command
delivery/acknowledgement states, and vitest + Playwright coverage.

Deliberate limitations: 10 s polling (no SSE); an acknowledgement proves the
junction device RECEIVED the command, never that a physical signal changed;
emergency CSV export streams from the server (the legacy client-side
`utils/csv.ts` helper is kept only as a reference).

## Stack

- Vite + React 19 + TypeScript (strict)
- react-router-dom (guarded routes) · @tanstack/react-query (API state)
- leaflet + react-leaflet (live map, lazy-loaded chunk)
- material-symbols icon font — **subset to the used ligatures**
  (`src/assets/material-symbols-subset.woff2`, ~240 KB vs ~3.8 MB; regenerate
  with `npm run icons:subset`, runs automatically in `prebuild`)
- vitest + @testing-library/react (unit) · @playwright/test (e2e, chromium)
- Plain CSS with custom properties (no Tailwind) — `src/styles/`

## Setup

```bash
npm install
npm run dev          # dev server with /api proxied to the backend
npm run build        # prebuild: icon subset → tsc -b (strict) + vite build
npm run lint         # oxlint
npm test             # vitest unit/component tests (src/**/*.test.*)
npm run test:watch   # vitest in watch mode
npm run test:e2e     # Playwright journeys (needs the demo backend, see below)
```

### Dev proxy and env files

In dev the portal calls same-origin `/api/v1`; Vite proxies `/api` →
`http://localhost:8000` (FastAPI) — see `vite.config.ts`. Set `VITE_API_URL`
in `.env.local` (see `.env.example`) to point at any other backend.

- `.env.local` — your local override (e.g. the Render backend).
- `.env.demo` — used by `npm run dev -- --mode demo` (Playwright): forces
  `VITE_API_URL=/api/v1` so the browser talks to the LOCAL demo backend
  same-origin — the portal-auth cookies require it.

## Login flow (portal-auth, contract §1/§9)

1. `POST /api/v1/portal-auth/login` `{ email, password }` →
   `{ success, data: { access_token, user { id, email, role, hospital_id,
   junction_ids } } }`. The access token is held in **module memory only**
   (`src/services/portalAuth.ts`) — never localStorage. The server sets the
   HttpOnly `portal_rt` refresh cookie and the readable `portal_csrf` cookie.
2. Boot: `POST /portal-auth/refresh` (cookie + `X-CSRF-Token` header) →
   `GET /auth/me`. A network failure shows a retry screen; an invalid session
   lands on `/login`.
3. `driver` logins are rejected server-side (`403 DRIVER_ROLE_NOT_ALLOWED`)
   and by the client guard (`ROLE_NOT_ALLOWED`).
4. On any mid-session `401`, `src/services/api.ts` runs a **single-flight**
   `POST /portal-auth/refresh` and retries once; if the refresh fails the
   user state + React Query cache are cleared and every other tab is told via
   `BroadcastChannel("portal-auth")` (`{type:"logout"}` / `{type:"expired"}`)
   — no stale authenticated screen survives.
5. Logout (`POST /portal-auth/logout`, best effort) revokes the server
   session, clears cookies and resets React Query state.
6. The legacy `localStorage["admin-portal:tokens:v1"]` key is deleted on
   first load so pre-portal-auth users get a clean sign-in.

All requests go through `request<T>()`, which unwraps the backend envelope and
throws `ApiError { message, status, code }` from
`{ success, data, error: { code, message } }`.

## Roles & navigation

| Role | Sidebar |
|---|---|
| **ADMIN** | Dashboard, Live Map, Emergencies, Users, Hospitals, Junctions, Devices, Fleet, Analytics, Audit, System |
| **HOSPITAL** | Dashboard, Live Tracking, My Fleet, Drivers, Emergencies, Alerts, Settings |
| **POLICE** | Dashboard, My Junctions, Command Log, Device Health, Analytics, Settings |

Nav items render per role and routes are guarded: unauthenticated → redirect
`/login`; a wrong-role deep link is blocked and redirects to the user's
dashboard. Scoping is always enforced server-side; the UI guards are UX only.
Heavy routes (map/analytics/audit/system/devices) are React.lazy split behind
a Suspense spinner; `/login` and the dashboards stay eager.

When `GET /portal/status` reports `simulation: true` (DEMO_MODE=1 backend), a
**Simulation** badge appears in the top bar.

## Demo backend + e2e (Playwright)

The journeys in `e2e/` (admin / hospital / police / auth) run against the
isolated demo backend (contract §8). From the repo root:

```bash
# 1. Local PostgreSQL demo database (docker-compose provides demo_db)
# 2. Seed + start the backend with DEMO_MODE=1 (never loads server/.env):
cd server
DEMO_MODE=1 uv run alembic upgrade head
DEMO_MODE=1 uv run python -m scripts.simulator --seed-only
DEMO_MODE=1 uv run uvicorn app.main:app --port 8000
# 3. Run the browser tests (starts `vite dev --mode demo` itself):
cd ../admin && npm run test:e2e
```

Seeded demo users: `admin@demo.io / Admin123!`,
`hospital@demo.io / Hospital123!`, `police@demo.io / Police123!`,
`driver@demo.io / Demo123!` (rejected by the portal).

Unit tests (`npm test`) need no backend — network calls are mocked.

## Production (Vercel)

Standalone deployment: Vite `base` is `/`, and `vercel.json` rewrites
`/api/(.*)` → `https://seedgrant-backend.onrender.com/api/$1` **before** the
SPA fallback, so the portal and its portal-auth cookies are same-origin in
production too. Create a Vercel project with Root Directory `admin/`, build
`npm ci && npm run build`, output `dist`; no `VITE_API_URL` is required when
using the rewrite (set it only to bypass the proxy). Add the Vercel URL to
the backend's `CORS_ORIGINS` on Render (the refresh endpoint validates the
`Origin` header against the allowlist).

## Structure

```
admin/src/
├── app/          # AuthProvider + useAuth, nav config, guards, shell layout
├── components/   # ui.tsx (kit: Drawer focus trap, ConfirmDialog) + helpers
├── pages/        # LoginPage + adminRoutes/portalRoutes (+ routes-lazy) + admin/, hospital/, police/, shared/
├── services/     # portalAuth.ts (memory session/CSRF/broadcast) + api.ts + portal.ts (endpoints)
├── styles/       # theme.css (tokens + @font-face subset), ui.css, layout.css
├── types/        # api.ts (auth/envelope) + portal.ts (portal contracts)
├── utils/        # csv.ts (client-side CSV reference implementation)
└── main.tsx      # providers: QueryClient → BrowserRouter → AuthProvider
admin/scripts/    # subset-icons.mjs (icon ligature subsetter)
admin/e2e/        # Playwright journeys (admin/hospital/police/auth)
```
