"""users.role back to VARCHAR(16) — ORM compatibility forward-fix for 0009

Forward fix (plan §5: forward-fix strategy, never rewrite migrations).
Migration 0009 converted users.role to the portal_role_lc ENUM, but the ORM
model declares String(16); every INSERT from the app (register/seed) then
fails on Postgres with DatatypeMismatchError ("column role is of type
portal_role_lc but expression is of type character varying"). Convert the
column back to VARCHAR(16) and enforce 0009's lowercase-value intent with a
CHECK constraint instead — ORM binds work unchanged on Postgres and SQLite.
The portal_role_lc type itself is left in place (harmless).
"""
# ruff: noqa: E402, I001 — alembic revision vars precede imports by convention
revision = "0014_role_varchar_compat"
down_revision = "0013_command_deliveries"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(16) USING role::text")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'driver'")
    op.execute(
        "DO $$ BEGIN "
        "ALTER TABLE users ADD CONSTRAINT ck_users_role_lc "
        "CHECK (role IN ('admin','hospital','police','driver')); "
        "EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; END $$"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role_lc")
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE portal_role_lc AS ENUM ('admin','hospital','police','driver'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE portal_role_lc USING role::portal_role_lc")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'driver'::portal_role_lc")
