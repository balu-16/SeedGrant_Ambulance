# SeedGrant — Emergency Vehicle Priority System

An emergency-response platform: ambulances stream GPS during an emergency, the backend
detects the junction being approached and issues priority commands (via MQTT / device
polling) so the junction's Raspberry Pi controller can clear the way.

## Repository layout

| Path | What it is |
|---|---|
| `server/` | FastAPI backend (Python 3.12, SQLAlchemy async, PostgreSQL/Supabase, Alembic, MQTT, Expo push). See `server/README.md`. |
| `client/` | Expo (React Native) driver app — onboarding, login, home (emergency session + GPS), history, profile. Has its **own git repository**. See `client/README.md`. |
| `reference/` | UI design mockups the client implements (splash, login, home, history, profile). |
| `FastAPI Backend Implementation Prompt.md` | The original backend implementation spec. Note: the backend's `/vision/*` YOLO endpoints and the Expo client were built beyond it (the spec reserved inference for the Raspberry Pi). |
| `best.pt` | YOLO weights used by `server/app/services/detect.py` (`/vision/detect`). Kept out of version control (`*.pt` is gitignored). |

## Secrets policy (important)

- `server/.env` holds real credentials (Supabase, MQTT broker, JWT secret). It is
  gitignored — never commit, zip, or share it.
- `seedgrant-9dc6f-firebase-adminsdk-*.json` at the repo root is a **live Firebase
  service-account private key**. It is gitignored. It is **not required** for Expo push
  (the Expo Push Service talks to FCM for you) — it is only needed if the backend ever
  calls the FCM v1 API directly. If it was ever shared, rotate it in the Google Cloud
  console (IAM & Admin → Service Accounts → Keys).
- If any credential in `server/.env` was ever exposed, rotate it (Supabase service key,
  EMQX app secret, JWT secret).

## Quick start

### Backend

```bash
cd server
uv venv && uv pip install -e .          # or: uv sync
cp .env.example .env                    # then fill in real values
alembic upgrade head
python -m app.db.seed                   # seeds junction, approaches, device, demo users
pytest                                  # unit + integration tests
python main.py                          # serves on :8000 (docs at /docs)
```

Demo accounts created by the seed: admin `admin@seedgrant.local / Admin123!`,
driver `driver@seedgrant.local / Demo123!` (change before any real deployment).

### Client

```bash
cd client
npm install
npm start                               # Expo dev server
npm run typecheck && npm test           # tsc --noEmit + unit tests
```

The app runs fully offline as a demo by default; set `EXPO_PUBLIC_API_URL` in
`client/.env` to link it to the backend (real login, GPS streaming, history, push).
