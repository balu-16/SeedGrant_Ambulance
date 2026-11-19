"""portal_sessions — server-side dashboard sessions for the cookie-based portal auth flow

Requires `alembic upgrade head` before deploy. Schema expansion only; no
backfill. Browser holds only an opaque HttpOnly refresh cookie; this table
stores its SHA-256 hash plus a per-session CSRF token hash.
"""
# ruff: noqa: E402, I001 — alembic revision vars precede imports by convention
revision = "0011_portal_sessions"
down_revision = "0010_composite_index_parity"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade() -> None:
    op.create_table(
        "portal_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_portal_sessions_user_id", "portal_sessions", ["user_id"])
    op.create_index("ix_portal_sessions_refresh_token_hash", "portal_sessions", ["refresh_token_hash"], unique=True)
    op.create_index("ix_portal_sessions_expires_at", "portal_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_portal_sessions_expires_at", table_name="portal_sessions")
    op.drop_index("ix_portal_sessions_refresh_token_hash", table_name="portal_sessions")
    op.drop_index("ix_portal_sessions_user_id", table_name="portal_sessions")
    op.drop_table("portal_sessions")
