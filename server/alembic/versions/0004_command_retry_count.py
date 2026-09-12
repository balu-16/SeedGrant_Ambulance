"""add retry_count to emergency_commands

requires `alembic upgrade head` before deploy
"""
# ruff: noqa: E402, I001 — alembic revision vars precede imports by convention
revision = "0004_command_retry_count"
down_revision = "0003_app_completion"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        "emergency_commands",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("emergency_commands", "retry_count")
