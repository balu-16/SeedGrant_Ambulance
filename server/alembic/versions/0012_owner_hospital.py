"""emergency_sessions.owner_hospital_id — ownership snapshot at session start

Requires `alembic upgrade head` before deploy. Nullable FK: null on
pre-migration records (admin-only visibility until an admin review assigns
one) and for ambulances without a hospital. NO automatic backfill —
historical ownership is only ever set by the explicit admin review action.
"""
# ruff: noqa: E402, I001 — alembic revision vars precede imports by convention
revision = "0012_owner_hospital"
down_revision = "0011_portal_sessions"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade() -> None:
    op.add_column(
        "emergency_sessions",
        sa.Column("owner_hospital_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_sessions_owner_hospital",
        "emergency_sessions",
        "hospitals",
        ["owner_hospital_id"],
        ["id"],
    )
    op.create_index("ix_sessions_owner_hospital", "emergency_sessions", ["owner_hospital_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_owner_hospital", table_name="emergency_sessions")
    op.drop_constraint("fk_sessions_owner_hospital", "emergency_sessions", type_="foreignkey")
    op.drop_column("emergency_sessions", "owner_hospital_id")
