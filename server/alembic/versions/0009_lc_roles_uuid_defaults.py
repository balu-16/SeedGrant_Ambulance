"""lowercase role ENUM + UUID server defaults for dashboard inserts

Live Supabase already has portal_role_lc + gen_random_uuid() defaults
(applied out-of-band); this migration makes alembic-managed DBs match so a
fresh `alembic upgrade head` produces the same schema. Idempotent guards keep
it safe to run on the live DB.
"""
# ruff: noqa: E402, I001 — alembic revision vars precede imports by convention
revision = "0009_lc_roles_uuid_defaults"
down_revision = "0008_last_login_prefs"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


UUID_TABLES = [
    "users",
    "ambulances",
    "junctions",
    "approaches",
    "devices",
    "telemetry",
    "heartbeats",
    "emergency_sessions",
    "gps_points",
    "emergency_commands",
    "audit_logs",
    "push_subscriptions",
    "driver_profiles",
    "detections",
    "hospitals",
    "police_assignments",
    "emergency_contacts",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE portal_role_lc AS ENUM ('admin','hospital','police','driver'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    for tbl in UUID_TABLES:
        op.execute(
            f"ALTER TABLE {tbl} ALTER COLUMN id SET DEFAULT gen_random_uuid()"
        )
    op.execute("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT true")
    op.execute("ALTER TABLE users ALTER COLUMN created_at SET DEFAULT now()")
    # Live DB already has portal_role_lc (applied out-of-band); fresh DBs have
    # VARCHAR. lower() has no ENUM overload, so cast to text first, and skip
    # the TYPE conversion entirely when the column is already the ENUM.
    op.execute(
        "DO $$ DECLARE cur_type text; BEGIN "
        "SELECT udt_name INTO cur_type FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='users' AND column_name='role'; "
        "IF cur_type IS DISTINCT FROM 'portal_role_lc' THEN "
        "UPDATE users SET role = lower(role::text) WHERE role IS NOT NULL; "
        "ALTER TABLE users ALTER COLUMN role DROP DEFAULT; "
        "ALTER TABLE users ALTER COLUMN role TYPE portal_role_lc "
        "USING lower(role::text)::portal_role_lc; "
        "END IF; "
        "END $$"
    )
    op.execute(
        "ALTER TABLE users ALTER COLUMN role SET DEFAULT 'driver'::portal_role_lc"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(16) USING role::text"
    )
