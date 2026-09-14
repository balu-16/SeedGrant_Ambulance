# SeedGrant — Emergency Vehicle Priority System

Monorepo. Ambulances stream GPS during an emergency, the backend detects the
junction being approached and issues priority commands (via MQTT / device
polling) so the junction's Raspberry Pi controller can clear the way.
Spec: `project.md`.

## Layout

| Path | What it is | Deploy |
|---|---|---|
| `server/` | FastAPI backend (Python 3.12, SQLAlchemy async, PostgreSQL, Alembic, MQTT, Expo push). See `server/README.md`. | Render (`seedgrant-backend`) |
| `admin/` | Vite + React portal (ADMIN / HOSPITAL / POLICE). See `admin/README.md`. | Vercel (root dir `admin/`) |
| `client/` | Expo (React Native) driver app. See `client/README.md`. | Expo / EAS |
| `raspberryPi/` | Pi 5 edge controller (YOLO + tracking + adaptive signals). See `raspberryPi/README.md`. | SD-card / systemd |
| `docker-compose.yml` | Local PostgreSQL 16 (`docker compose up -d db`). | local only |

Inference runs on the Pi (edge) and is ingested via
`POST /api/v1/vision/detections`; the backend runs no model. Weights
(`best.pt` / `best.onnx`) live in `raspberryPi/weights/` and are gitignored.

## Quick start (each folder is independent)

```bash
# Backend (Render mirrors this, minus seed)
cd server && uv sync && cp .env.example .env && alembic upgrade head \
  && python -m app.db.seed && pytest && python main.py   # :8000, /docs

# Admin portal (Vercel mirrors this)
cd admin && npm install && npm run dev                    # :5173 → proxies /api to :8000

# Driver app
cd client && npm install && npm start                     # Expo dev server

# Pi edge
cd raspberryPi && cp .env.example .env && pip install -r requirements-pi.txt && python src/main.py
```

Demo accounts (seed): admin `admin@demo.io / Admin123!`,
driver `driver@demo.io / Demo123!` — change before any real deployment.

## Secrets policy

All of these are gitignored — never commit, zip, or share them:

- `server/.env` (Supabase, MQTT broker, JWT secret). If ever exposed, rotate
  the Supabase service key, MQTT secret, and JWT secret.
- `client/.env` (`EXPO_PUBLIC_API_URL` wiring is in `.env.example`).
- `raspberryPi/.env` (device API key per Pi).
- `seedgrant-9dc6f-firebase-adminsdk-*.json` — live Firebase private key that
  no code uses (push goes through Expo Push Service). Rotate in Google Cloud
  console (IAM → Service Accounts → Keys) and move it out of the repo.

## Deploy map

- **Backend → Render**: repo root cloned, build `cd server && …`, start
  `cd server && uv run uvicorn app.main:app`. `CORS_ORIGINS` must include the
  Vercel URL.
- **Admin → Vercel**: new project, Root Directory `admin/`, build
  `npm ci && npm run build`, output `dist`, env
  `VITE_API_URL=https://seedgrant-backend.onrender.com/api/v1`.
- **Driver → EAS/Expo**: standard Expo builds from `client/`.
