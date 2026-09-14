# SeedGrant Admin — web control portal

Desktop-first admin portal for the SeedGrant emergency traffic priority system,
serving three personas — **ADMIN**, **HOSPITAL**, **POLICE** (DRIVER accounts
use the Expo app in `client/`, never this portal). Built in the same visual
language as the driver app: design tokens are copied verbatim from
`client/constants/theme.ts` and the UI kit mirrors `client/components/ui.tsx`.

**Status: complete.** All three persona page sets (ADMIN / HOSPITAL / POLICE)
are implemented and wired to the live backend: live map, emergencies with
timelines + CSV export, users/hospitals/junctions management, fleet, device
health with telemetry drawers, alerts, analytics, audit, command log with
manual overrides, and settings. Not implemented (deliberately): SSE live
streams (10 s polling is used instead) and portal e2e tests.

## Stack

- Vite + React 19 + TypeScript (strict)
- react-router-dom (guarded routes) · @tanstack/react-query (API state)
- leaflet + react-leaflet (live map, wired in phase 3)
- material-symbols (self-hosted icon font — web counterpart of the app's
  MaterialCommunityIcons)
- Plain CSS with custom properties (no Tailwind) — `src/styles/`

## Setup

```bash
npm install
npm run dev       # dev server with /api proxied to the backend
npm run build     # tsc -b (strict) + vite build → dist/
npm run lint      # oxlint
npm run preview   # serve the production build locally
```

### Dev proxy

In dev the portal calls same-origin `/api/v1`; Vite proxies `/api` →
`http://localhost:8000` (FastAPI) — see `vite.config.ts`. So run the backend on
port 8000 and log in with a seeded portal account. Set `VITE_API_URL` in
`.env.local` (see `.env.example`) to point at any other backend.

## Roles & navigation

| Role | Sidebar |
|---|---|
| **ADMIN** | Dashboard, Live Map, Emergencies, Users, Hospitals, Junctions, Devices, Fleet, Analytics, Audit, System |
| **HOSPITAL** | Dashboard, Live Tracking, My Fleet, Drivers, Emergencies, Alerts, Settings |
| **POLICE** | Dashboard, My Junctions, Command Log, Device Health, Analytics, Settings |

Nav items render per role and routes are guarded: unauthenticated → redirect
`/login`; a wrong-role deep link is blocked and redirects to the user's
dashboard. Scoping is always enforced server-side; the UI guards are UX only.

## Login flow contract (for the phases that wire real endpoints)

1. `POST /api/v1/auth/login` `{ email, password }` →
   `{ success, data: { access_token, refresh_token, user { id, email, role } } }`.
   Tokens are stored under `localStorage["admin-portal:tokens:v1"]`.
2. `GET /api/v1/auth/me` (Bearer) re-verifies the account server-side; the
   returned user (role ∈ `ADMIN | HOSPITAL | POLICE`) drives the nav, the
   role chip and the route guards.
3. `DRIVER` logins are rejected client-side (`ROLE_NOT_ALLOWED`) — the mobile
   app is their client.
4. On any `401`, `src/services/api.ts` runs a **single-flight**
   `POST /auth/refresh` `{ refresh_token }` and retries the original request
   once; if the refresh fails, tokens are cleared and `RequireAuth` redirects
   to `/login`.
5. Logout clears tokens (`POST /auth/logout` best-effort) and resets React
   Query state.

All requests go through `request<T>()`, which unwraps the backend envelope and
throws `ApiError { message, status, code }` from
`{ success, data, error: { code, message } }`.

## Production (Vercel)

Standalone deployment: Vite `base` is `/`, backend comes from `VITE_API_URL`,
and `vercel.json` provides the SPA fallback. Create a Vercel project with
Root Directory `admin/`, build `npm ci && npm run build`, output `dist`, and
env `VITE_API_URL=https://seedgrant-backend.onrender.com/api/v1`.
Add the Vercel URL to the backend's `CORS_ORIGINS` on Render.

## Structure

```
admin/src/
├── app/          # AuthProvider + useAuth, nav config, guards, shell layout
├── components/   # ui.tsx (kit mirroring client/components/ui.tsx) + helpers
├── pages/        # LoginPage + portalRoutes/adminRoutes + admin/, hospital/, police/, shared/
├── services/     # tokenStorage (localStorage) + api.ts (request/refresh) + portal.ts (endpoints)
├── styles/       # theme.css (app tokens verbatim), ui.css, layout.css
├── types/        # api.ts (auth/envelope) + portal.ts (portal contracts)
├── utils/        # csv.ts (client-side CSV export)
└── main.tsx      # providers: QueryClient → BrowserRouter → AuthProvider
```
