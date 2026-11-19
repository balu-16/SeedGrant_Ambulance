# Edge-AI Traffic Backend (FastAPI + Supabase Postgres)

Central API for ambulance priority. Pis do YOLO/edge decisions locally; backend coordinates.

Data layer: **SQLAlchemy 2.0 async ORM** over `asyncpg` — one `AsyncSession` per request via a
FastAPI dependency, declarative models in `app/models/` (16 tables, UUID PKs, JSONB payloads),
schema managed by Alembic (sync `psycopg` URL). The test suite runs on in-memory SQLite, so
`pytest` needs no live database.

## Setup — paste keys, zero errors

```bash
cd server
uv venv
source .venv/bin/activate   # venv has no pip; installs via uv pip (see below)
uv sync
cp .env.example .env   # replace every PASTE_* (see below)
python scripts/check_env.py   # preflight: fails with per-var guidance
alembic upgrade head
python -m app.db.seed
python -m pytest
python main.py                # serve on 0.0.0.0:8000 (flags: --port, --reload)
```

Local Postgres without Supabase: `docker compose up -d db` from the repo root, then set
`DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/trafficdb` and the
matching `SYNC_DATABASE_URL` in `.env`.

Run the live end-to-end check against real Supabase (needs DB access):
```bash
python scripts/live_test.py --base http://localhost:8000
```

Seed: Benz Circle Vijayawada `16.5058, 80.6520`, driver `driver@demo.io / Demo123!`,
admin `admin@demo.io / Admin123!`, ambulance `AP39-0001`, device `PI-BENZ-01`.

## Keys to paste (where to get each)

| Var | Source |
|---|---|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard → Settings → API |
| `DATABASE_URL` | Supabase pooler asyncpg URL `:6543 ?ssl=require` |
| `SYNC_DATABASE_URL` | Supabase direct URI `:5432` (Database → Connect) |
| `JWT_SECRET` | `openssl rand -hex 32` (≥32 chars) |
| `MQTT_*` + `MQTT_PROVIDER=real` | EMQX/HiveMQ cluster connection info (`ENVIRONMENT=prod` refuses to boot with `MQTT_PROVIDER=mock`) |
| Tuning (optional) | `GPS_MAX_AGE_SECONDS`, `MAX_COMMAND_RETRIES`, `SWEEP_MIN_INTERVAL_SECONDS`, `DATA_RETENTION_DAYS`, `RATE_LIMIT_ENABLED`, `RATE_LIMIT_AUTH_PER_MINUTE`, `TRUST_PROXY_HEADERS`, `MQTT_OUTBOX_MAX`, `MQTT_RECONNECT_MAX_DELAY_SECONDS`, `JWT_ISSUER`, `JWT_AUDIENCE` |

Providers default to `mock` so everything boots/tests without keys.

## Driver mobile flow (Expo app in `../client`)

```
POST /api/v1/auth/login {email, password} → {access_token, refresh_token, user}
→ app asks OS notification permission (expo-notifications)
→ POST /api/v1/push/register {player_id, expo_push_token, device_type}  (Bearer access token)
→ Start Emergency → backend pushes to stored player_ids
→ POST /api/v1/auth/logout  (revokes refresh tokens)
```

Public `POST /auth/register` always creates a DRIVER account — admins exist via the
seed only. Refresh tokens rotate on every refresh; a rotated token is rejected.

## APIs (`/api/v1`)

- `POST /auth/register|login|refresh|logout|change-password`, `GET /auth/me`,
  `GET|PATCH /auth/profile` (driver profile)
- `POST|GET|DELETE /push/*` (push-token register/list/remove)
- `POST /ambulances`, `GET /ambulances`, `GET /ambulances/mine`, `GET|PATCH /ambulances/{id}`
- `POST /junctions`, `GET /junctions`, `GET /junctions/{id}`, `POST /junctions/{id}/override`
- `GET /hospitals`, `GET /hospitals/{id}` (destination picker — read-only; HOSPITAL users are scoped to their own hospital)
- `POST /admin/devices/register` (returns api_key once), `POST /admin/devices/{id}/rotate-key`
- `POST /devices/heartbeat|telemetry` (`X-Device-Api-Key`)
- `GET /junctions/{id}/state`, `GET /telemetry?junction_id&limit&offset`
- `POST /emergencies/start`, `POST /emergencies/{id}/gps`, `GET /emergencies/current`,
  `POST /emergencies/{id}/stop|cancel|heartbeat|patient`, `GET /emergencies/{id}/timeline`,
  `GET /emergencies/history`
- `GET /commands/pending?junction_id`, `POST /commands/{id}/ack`, `GET /commands/admin/list`
- `POST /admin/sweep`, `GET /admin/config-check`, `GET /admin/mqtt/health`,
  `GET /admin/devices/status`, `GET /admin/emergencies`, `GET /admin/fleet/drivers`,
  `GET|POST /admin/users`, `PATCH /admin/users/{id}`, `POST /admin/users/{id}/password-reset`,
  `GET|POST /admin/hospitals`, `PATCH /admin/hospitals/{id}`, `GET /admin/live`,
  `GET /admin/alerts`, `GET /admin/analytics/overview`, `GET /admin/audit`
- `POST|GET /vision/detections` (Pi-side inference ingest + portal listing; the server runs no model)
- `GET /health`, `GET /ready` (503 when DB down)

## Portal sessions (dashboard auth)

Portal roles (ADMIN/HOSPITAL/POLICE) sign in through `POST /portal-auth/login`
— driver accounts are rejected there. The server keeps a `portal_sessions`
row per login (SHA-256 hashed opaque refresh token + CSRF token hash), the
browser holds only an HttpOnly `portal_rt` cookie (SameSite=Lax, `Secure`
outside loopback dev) plus a readable `portal_csrf` cookie, and refresh/logout
must send `X-CSRF-Token` and a same-origin `Origin` (validated against
`CORS_ORIGINS`). Access tokens are short-lived JWTs (~15 min,
`PORTAL_ACCESS_TOKEN_MINUTES`) carrying a `sid` claim checked against session
revocation, so logout, password change/reset and account disable take effect
immediately. The driver `/auth/*` contract is unchanged — no cookies, no sid.

## Isolated demo / simulator (no live data, no hardware)

```bash
server/scripts/run_demo.sh        # docker compose db-demo (:5433) → alembic → seed → uvicorn on 127.0.0.1:8000
.venv/bin/python -m scripts.simulator --seed-only    # just (re)seed demo data
.venv/bin/python -m scripts.simulator                # full scripted journey (add --skip-long-waits to skip 5-min waits)
```

The journey drives the whole lifecycle against the running demo backend:
emergency start → GPS walk-in → PRIORITY_REQUEST → device poll + ack → HOLD
(release published, pending until acked) → REISSUE (attempt 2) →
FORCE_RELEASE → TTL expiry → inactivity timeout → device-offline — printing
PASS/FAIL per step, exit 1 on failure. Demo accounts:
`admin@demo.io/Admin123!`, `hospital@demo.io/Hospital123!`,
`police@demo.io/Police123!`, `driver@demo.io/Demo123!` (junction "Demo
Junction", ambulance DEMO-101; the device api key is printed once per seed).

Fail-closed gating: the backend refuses to boot with `DEMO_MODE=1` unless
`ENVIRONMENT=dev`, `MQTT_PROVIDER=mock` and both DB URLs point at a localhost
`*demo*` database; in demo mode `server/.env` is ignored entirely
(`get_settings` uses `_env_file=None`). The simulator re-validates the same
gates before seeding or sending anything and never touches push services.

## Migrations (0011–0014)

- `0011_portal_sessions` — server-side dashboard sessions.
- `0012_owner_hospital` — `emergency_sessions.owner_hospital_id` ownership
  snapshot (nullable; NO backfill — old records stay admin-only until the
  admin review action `PATCH /admin/emergencies/{id}/hospital-ownership`).
- `0013_command_deliveries` — per-attempt delivery rows persisted in the same
  transaction as the command state change, before the MQTT publish; adds
  `emergency_commands.junction_seq`.
- `0014_role_varchar_compat` — forward fix for 0009: `users.role` back to
  VARCHAR(16) + CHECK constraint (the portal_role_lc ENUM broke every ORM
  INSERT on Postgres; the live Supabase DB never applied 0009 so it never
  surfaced there). `alembic downgrade` reverses it.

Verify on a fresh DB and an upgraded-from-0010 DB before deploying:

```bash
alembic upgrade head   # fresh DB
alembic downgrade 0010_composite_index_parity && alembic upgrade head
```

## Tests

```bash
.venv/bin/python -m pytest          # 164 tests, hermetic SQLite + mock MQTT (no live services)
.venv/bin/ruff check app scripts tests
```

New suites: `test_portal_auth` (cookie/CSRF/origin/rotation/revocation),
`test_ownership` (snapshot, transfer guard, review action),
`test_emergency_filters_export` (filters, CSV escaping),
`test_command_lifecycle` (hold/reissue/force-release, idempotent acks,
stale attempts), `test_simulator_gating` (fail-closed demo gates).

## Known limitations

- A command acknowledgement proves the junction device RECEIVED the command —
  never that a physical signal changed. Manual controls are enabled only for
  the isolated demo (`DEMO_MODE=1`); real-device enablement is a separate
  hardware-validation effort.
- Alerts are a derived in-portal feed (no email/SMS/push advertisement).
- Pi camera/telemetry publishing is not wired into `raspberryPi/src/main.py`
  (no physical hardware in this phase); the simulator produces telemetry
  instead.

## Admin portal hosting

The portal deploys standalone on Vercel (see `../admin/README.md`) and calls
this API cross-origin via `VITE_API_URL`, so keep `CORS_ORIGINS` in sync with
the Vercel URL (the allowlist also gates the portal-refresh Origin check).
`../admin/vercel.json` rewrites `/api/*` here so portal cookies stay
same-origin in production. The Render image contains only the backend; the
portal is not served from FastAPI.
