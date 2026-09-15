"""composite index parity guards (0003/0007 indexes as IF NOT EXISTS)

Live Supabase already has these four indexes; fresh `create_all` DBs now also
declare them via __table_args__. This migration is a no-op on the live DB
(IF NOT EXISTS guards) and heals any alembic-managed DB that missed them.
Does NOT touch RLS or data.
"""
# ruff: noqa: E402, I001 — alembic revision vars precede imports by convention
revision = "0010_composite_index_parity"
down_revision = "0009_lc_roles_uuid_defaults"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sessions_driver_status_started "
        "ON emergency_sessions (driver_id, status, started_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_gps_session_recorded "
        "ON gps_points (session_id, recorded_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_detections_junction_detected "
        "ON detections (junction_id, detected_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contacts_user_position "
        'ON emergency_contacts (user_id, "position")'
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_contacts_user_position")
    op.execute("DROP INDEX IF EXISTS ix_detections_junction_detected")
    op.execute("DROP INDEX IF EXISTS ix_gps_session_recorded")
    op.execute("DROP INDEX IF EXISTS ix_sessions_driver_status_started")
