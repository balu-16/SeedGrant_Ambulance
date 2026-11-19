#!/usr/bin/env bash
# SeedGrant DEMO backend runner (plan §4.7 / contract §7).
#
# Starts ONLY the isolated demo database, applies migrations to it, and then
# execs the backend with a hard demo configuration. The demo backend must
# never read the developer's live server/.env (DEMO_MODE=1 makes get_settings
# ignore it) and never touches live infrastructure (validated at startup).
#
# Usage:
#     server/scripts/run_demo.sh
#
# Then (separately): seed + journey via the simulator:
#     cd server && .venv/bin/python -m scripts.simulator            # full journey
#     cd server && .venv/bin/python -m scripts.simulator --seed-only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SERVER_DIR/.." && pwd)"

DEMO_ASYNC_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/trafficdb_demo"
DEMO_SYNC_URL="postgresql+psycopg://postgres:postgres@localhost:5433/trafficdb_demo"

echo "[run_demo] starting demo database container (db-demo) — nothing else is started"
docker compose -f "$REPO_ROOT/docker-compose.yml" up -d db-demo

echo "[run_demo] waiting for seedgrant-db-demo to become healthy ..."
for i in $(seq 1 60); do
  status="$(docker inspect --format '{{.State.Health.Status}}' seedgrant-db-demo 2>/dev/null || true)"
  if [ "$status" = "healthy" ]; then
    echo "[run_demo] database healthy (after ${i}s)"
    break
  fi
  if [ "$i" = "60" ]; then
    echo "[run_demo] FATAL: demo database did not become healthy" >&2
    exit 1
  fi
  sleep 1
done

# Demo environment for BOTH alembic and uvicorn (exported so get_settings()
# sees DEMO_MODE=1 and ignores server/.env entirely).
export DEMO_MODE=1
export ENVIRONMENT=dev
export MQTT_PROVIDER=mock
export DATABASE_URL="$DEMO_ASYNC_URL"
export SYNC_DATABASE_URL="$DEMO_SYNC_URL"
export RATE_LIMIT_ENABLED=false

cd "$SERVER_DIR"
PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "[run_demo] FATAL: server/.venv not found — create the venv first" >&2
  exit 1
fi

echo "[run_demo] applying migrations to trafficdb_demo (alembic upgrade head)"
"$PY" -m alembic upgrade head

echo "[run_demo] seeding demo dataset (idempotent)"
"$PY" -m scripts.simulator --seed-only

echo "[run_demo] starting demo backend on http://127.0.0.1:8000 (Ctrl+C to stop)"
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
