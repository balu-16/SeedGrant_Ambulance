# SeedGrant — Emergency Vehicle Priority System

An emergency-response platform: ambulances stream GPS during an emergency, the backend
detects the junction being approached and issues priority commands (via MQTT / device
polling) so the junction's Raspberry Pi controller can clear the way.

## Repository layout

| Path | What it is |
|---|---|
| `server/` | FastAPI backend (Python 3.12, SQLAlchemy async, PostgreSQL/Supabase, Alembic, MQTT, Expo push). Also serves the built admin portal at `/admin`. See `server/README.md`. |
| `client/` | Expo (React Native) driver app — onboarding, login, home (emergency session + GPS), history, profile. **Nested git repository** (not tracked by the outer repo — clone/push it separately). See `client/README.md`. |
| `admin/` | Vite + React admin portal (ADMIN / POLICE / HOSPITAL personas). Built with `npm run build`; served by the backend at `http://localhost:8000/admin/`. See `admin/README.md`. |
| `docker-compose.yml` | Local PostgreSQL 16 (`docker compose up -d db`) so the backend can run without a Supabase account. |

Backend architecture note: inference runs on the Raspberry Pi (edge) and is ingested via
`POST /api/v1/vision/detections`; the backend itself runs no model. (`best.pt` at the repo
root is left over from a demo — it is gitignored and nothing in the repo uses it; safe to
delete.)

## Secrets policy (important)

- `server/.env` holds real credentials (Supabase, MQTT broker, JWT secret). It is
  gitignored — never commit, zip, or share it.
- `seedgrant-9dc6f-firebase-adminsdk-*.json` at the repo root is a **live Firebase
  service-account private key** that no code uses (push goes through the Expo Push
  Service). It is gitignored — rotate it in the Google Cloud console (IAM & Admin →
  Service Accounts → Keys) and move it out of this directory.
- If any credential in `server/.env` was ever exposed, rotate it (Supabase service key,
  EMQX app secret, JWT secret).

## Quick start

### Backend

```bash
cd server
uv sync                                  # creates .venv and installs app + dev deps
cp .env.example .env                     # then fill in real values
alembic upgrade head
python -m app.db.seed                    # seeds junction, approaches, device, demo users
pytest                                   # unit + integration tests
python main.py                           # serves on :8000 (docs at /docs)
```

Demo accounts created by the seed: admin `admin@demo.io / Admin123!`,
driver `driver@demo.io / Demo123!` (change before any real deployment).

### Admin portal

```bash
cd admin
npm install
npm run dev                              # dev server at http://localhost:5173/admin/ (proxies /api → :8000)
npm run build                            # output in admin/dist — served by the backend at /admin/
```

### Client

```bash
cd client
npm install
npm start                               # Expo dev server
npm run typecheck && npm test           # tsc --noEmit + unit tests
```

The app runs fully offline as a demo by default; set `EXPO_PUBLIC_API_URL` in
`client/.env` to link it to the backend (real login, GPS streaming, history, push).

## Development infrastructure

- `LICENSE` — MIT.
- `.editorconfig` — shared editor defaults (4-space Python, 2-space JS/TS).
- Both repositories have **no git remote configured** — create private remotes and push
  both (outer repo and `client/`) before relying on them.
