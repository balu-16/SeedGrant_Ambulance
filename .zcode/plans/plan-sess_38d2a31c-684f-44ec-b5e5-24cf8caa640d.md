ADMIN PORTAL — IMPLEMENTATION PLAN (full detail in the message above; file saved as ADMIN_PORTAL_PLAN.md on approval)

Summary of the approved direction:
- New top-level `admin/` folder: Vite + React 19 + TypeScript strict SPA (sibling of client/ and server/), served in production by FastAPI as static files at /admin (single origin, existing middleware applies).
- UI mirrors the driver app: exact theme tokens from client/constants/theme.ts as CSS variables, component kit mirroring client/components/ui.tsx (Card, Badge, Button, Field, Timeline, Drawer, Empty, Header), navy sidebar layout, login page like reference/LoginPage.png.
- Backend: migration 0005 (hospitals table, police_assignments, hospital_id FKs), new roles HOSPITAL + POLICE (admin-created only), server-side scoping on every query, new endpoints: /admin/users, /admin/hospitals, scoped /ambulances, /admin/live, /admin/alerts, /admin/analytics/overview, /admin/audit, /junctions/{id}/override, extended /commands/admin/list + /junctions CRUD + /vision/detections.
- Personas: ADMIN (full control: users, hospitals, junctions, devices, fleet, analytics, audit, system), HOSPITAL (own fleet live tracking, fleet/driver management, history + CSV, alerts), POLICE (assigned junctions live state, command log, device health, manual override with reason + audit).

Build order (each phase verified before the next):
1. Backend foundation: migration 0005, role extensions, scoped require helpers, /admin/users + /admin/hospitals + scoped /ambulances — with pytest tests.
2. Portal scaffold: admin/ Vite app, theme.css from app tokens, UI kit, login page, guarded layout, API client with refresh-on-401.
3. ADMIN core pages: Dashboard, Live Map (react-leaflet + OSM), Emergencies + detail drawer, Users, Junctions, Devices, Fleet, Analytics, Audit.
4. HOSPITAL role pages: Dashboard, Live Tracking, My Fleet, Drivers, Emergencies + export, Alerts, Settings.
5. POLICE role pages: junction Dashboard, Junction Detail/Live, Manual Override, Command Log, Device Health, Analytics.
6. Realtime & polish: SSE for live map/alerts, CSV exports, responsive pass, Playwright e2e for the portal.

Housekeeping first (from the approved finishing steps of the fix campaign): when the test-suite agent finishes, verify its work, run the full final verification (pytest green, ruff, import, tsc, client tests), clean stale caches, and make the root repo's initial commit — then start Phase 1 of the portal.