"""emergency contacts: SOS recipients per user (max 5 enforced in the API)

requires `alembic upgrade head` before deploy.
"""
# ruff: noqa: E402, I001 — alembic revision vars precede imports by convention
revision = "0007_emergency_contacts"
down_revision = "0006_active_guards"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade() -> None:
    op.create_table(
        "emergency_contacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_contacts_user_position", "emergency_contacts", ["user_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_contacts_user_position", table_name="emergency_contacts")
    op.drop_table("emergency_contacts")
