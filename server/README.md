# Edge-AI Traffic Backend (FastAPI + Supabase Postgres)

Central API for ambulance priority. Pis do YOLO/edge decisions locally; backend coordinates.

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

- `POST /auth/register|login|refresh|logout`, `GET /auth/me`
- `POST|GET|DELETE /push/*` (push-token register/list/remove)
- `POST /ambulances`, `GET /ambulances/mine`, `GET /ambulances/{id}`
- `POST /junctions`, `GET /junctions`, `GET /junctions/{id}`
- `POST /admin/devices/register` (returns api_key once), `POST /admin/devices/{id}/rotate-key`
- `POST /devices/heartbeat|telemetry` (`X-Device-Api-Key`)
- `GET /junctions/{id}/state`, `GET /telemetry?junction_id&limit&offset`
- `POST /emergencies/start`, `POST /emergencies/{id}/gps`, `GET /emergencies/current`,
  `POST /emergencies/{id}/stop|cancel`, `GET /emergencies/history`
- `GET /commands/pending?junction_id`, `POST /commands/{id}/ack`, `GET /commands/admin/list`
- `GET /admin/devices/status`, `GET /admin/emergencies`, `POST /admin/sweep`, `GET /admin/config-check`
- `POST|GET /vision/detections` (Pi-side inference ingest + portal listing; the server runs no model)
- `GET /health`, `GET /ready` (503 when DB down)

## Admin portal hosting

After `cd ../admin && npm run build`, the API serves the portal at
`http://localhost:8000/admin/` (SPA fallback included) — same origin, so the portal's
`/api/v1` base needs no CORS. Dev alternative: `npm run dev` in `admin/` (Vite proxies
`/api` to :8000).
