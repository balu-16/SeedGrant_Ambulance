"""command_deliveries + emergency_commands.junction_seq — durable per-attempt delivery state

Requires `alembic upgrade head` before deploy. Every publish/poll attempt of a
command gets a delivery row persisted in the same transaction as the command
state change, before the MQTT publish, so retries/broker loss cannot lose or
duplicate deliveries silently. junction_seq is a per-junction monotonic
sequence assigned at insert (null only on pre-migration rows — no backfill).
"""
# ruff: noqa: E402, I001 — alembic revision vars precede imports by convention
revision = "0013_command_deliveries"
down_revision = "0012_owner_hospital"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade() -> None:
    op.add_column("emergency_commands", sa.Column("junction_seq", sa.Integer(), nullable=True))
    op.create_index(
        "ix_commands_junction_seq", "emergency_commands", ["junction_id", "junction_seq"]
    )
    op.create_table(
        "command_deliveries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "command_id",
            UUID(as_uuid=True),
            sa.ForeignKey("emergency_commands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("via", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PUBLISHED"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("command_id", "attempt", name="uq_deliveries_command_attempt"),
    )
    op.create_index("ix_deliveries_command_id", "command_deliveries", ["command_id"])


def downgrade() -> None:
    op.drop_index("ix_deliveries_command_id", table_name="command_deliveries")
    op.drop_table("command_deliveries")
    op.drop_index("ix_commands_junction_seq", table_name="emergency_commands")
    op.drop_column("emergency_commands", "junction_seq")
