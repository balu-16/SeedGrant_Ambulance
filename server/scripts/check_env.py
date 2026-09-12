"""Preflight: `uv run python scripts/check_env.py`. Fails with per-var guidance."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

errors: list[str] = []
warnings: list[str] = []


def need(name: str, value: str, hint: str, *, secret: bool = False) -> None:
    if not value or value.startswith("PASTE_"):
        errors.append(f"{name} is not set. {hint}")
    elif secret and len(value) < 16:
        warnings.append(f"{name} looks suspiciously short")


def main() -> int:
    from app.core.config import get_settings

    try:
        s = get_settings()
    except Exception as e:
        print(f"FATAL: cannot load settings: {e}")
        return 1

    need("DATABASE_URL", s.DATABASE_URL, "Paste Supabase pooler asyncpg URL (:6543, ?ssl=require).")
    need("SYNC_DATABASE_URL", s.SYNC_DATABASE_URL, "Paste Supabase direct psycopg URL (:5432).")
    if not s.SUPABASE_URL:
        warnings.append("SUPABASE_URL empty — REST features disabled, direct Postgres only.")
    if s.SUPABASE_ANON_KEY.startswith("PASTE_") or not s.SUPABASE_ANON_KEY:
        warnings.append("SUPABASE_ANON_KEY not set — only needed for Supabase REST/mobile later.")
    need(
        "SUPABASE_SERVICE_ROLE_KEY",
        s.SUPABASE_SERVICE_ROLE_KEY,
        "Dashboard → API → service_role (server only).",
        secret=True,
    )
    need("JWT_SECRET", s.JWT_SECRET, "Run: openssl rand -hex 32.", secret=True)
    if len(s.JWT_SECRET) < 32:
        errors.append("JWT_SECRET must be >= 32 chars.")

    if s.mqtt_is_real:
        need("MQTT_USERNAME", s.MQTT_USERNAME, "EMQX/HiveMQ cluster credentials.")
        need("MQTT_PASSWORD", s.MQTT_PASSWORD, "EMQX/HiveMQ cluster credentials.", secret=True)
        if "localhost" in s.MQTT_BROKER_URL:
            errors.append("MQTT_PROVIDER=real but MQTT_BROKER_URL still points at localhost.")
    else:
        print("MQTT_PROVIDER=mock — broker checks skipped (flip to real after pasting creds).")

    # DB reachability (sync driver, short timeout). Strip the SQLAlchemy
    # dialect prefix (+psycopg) which psycopg.connect cannot parse.
    try:
        import psycopg

        dsn = s.SYNC_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://").replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        conn = psycopg.connect(dsn, connect_timeout=8)
        conn.execute("SELECT 1")
        conn.close()
        print("DB reachable via SYNC_DATABASE_URL.")
    except Exception as e:
        errors.append(f"Cannot reach DB via SYNC_DATABASE_URL: {e}")

    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        print("\nERRORS:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nENV OK — safe to run: alembic upgrade head && seed && pytest && uvicorn.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
