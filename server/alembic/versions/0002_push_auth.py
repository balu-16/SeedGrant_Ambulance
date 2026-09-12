"""push_subscriptions + users.refresh_version"""
revision = "0002_push_auth"
down_revision = "0001_init"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade():
    op.add_column("users", sa.Column("refresh_version", sa.Integer(), server_default="0", nullable=False))
    op.create_table(
        "push_subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("player_id", sa.String(128), unique=True, index=True),
        sa.Column("device_type", sa.String(32), server_default=""),
        sa.Column("app_version", sa.String(32), server_default=""),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )


def downgrade():
    op.drop_table("push_subscriptions")
    op.drop_column("users", "refresh_version")
