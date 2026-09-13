"""concurrency guards: one ambulance per driver, one active session per ambulance/driver

requires `alembic upgrade head` before deploy. The partial unique indexes
assume clean data: a driver assigned to multiple ambulances, or two active
sessions sharing an ambulance/driver, will make this migration fail loudly —
fix those rows first (the app now prevents creating them).
"""
# ruff: noqa: E402, I001 — alembic revision vars precede imports by convention
revision = "0006_active_guards"
down_revision = "0005_admin_portal"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

# frozen snapshot of app.core.consts.ACTIVE_SESSION_STATUSES (migrations must
# not import app code that may change after this revision ships)
_ACTIVE_STATUSES = (
    "CREATED",
    "ACTIVE",
    "APPROACHING_JUNCTION",
    "PRIORITY_REQUESTED",
    "CROSSING",
)
_ACTIVE_SQL = ", ".join(f"'{s}'" for s in _ACTIVE_STATUSES)


def upgrade():
    op.create_index(
        "uq_ambulances_driver",
        "ambulances",
        ["driver_id"],
        unique=True,
        postgresql_where=sa.text("driver_id IS NOT NULL"),
    )
    op.create_index(
        "uq_emergency_sessions_ambulance_active",
        "emergency_sessions",
        ["ambulance_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({_ACTIVE_SQL})"),
    )
    op.create_index(
        "uq_emergency_sessions_driver_active",
        "emergency_sessions",
        ["driver_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({_ACTIVE_SQL})"),
    )


def downgrade():
    op.drop_index("uq_emergency_sessions_driver_active", table_name="emergency_sessions")
    op.drop_index("uq_emergency_sessions_ambulance_active", table_name="emergency_sessions")
    op.drop_index("uq_ambulances_driver", table_name="ambulances")
