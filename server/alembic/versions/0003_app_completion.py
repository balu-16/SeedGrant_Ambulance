"""app completion: driver_profiles, detections, expo_push_token, session context, indexes"""
# ruff: noqa: E402, I001 — alembic revision vars precede imports by convention
revision = "0003_app_completion"
down_revision = "0002_push_auth"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


def upgrade():
    op.create_table(
        "driver_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            index=True,
        ),
        sa.Column("name", sa.String(128), server_default=""),
        sa.Column("phone", sa.String(32), server_default=""),
        sa.Column("region", sa.String(128), server_default=""),
        sa.Column("hospital", sa.String(256), server_default=""),
        sa.Column("control_center", sa.String(256), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "detections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("emergency_sessions.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "junction_id",
            UUID(as_uuid=True),
            sa.ForeignKey("junctions.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("vehicle_class", sa.String(16), index=True),
        sa.Column("class_name", sa.String(32), server_default=""),
        sa.Column("confidence", sa.Float(), server_default="0"),
        sa.Column("bbox", JSONB, server_default="{}"),
        sa.Column(
            "detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True
        ),
    )
    op.add_column(
        "push_subscriptions", sa.Column("expo_push_token", sa.String(128), nullable=True)
    )
    op.create_index(
        "ix_push_expo_token", "push_subscriptions", ["expo_push_token"]
    )
    # backfill Expo-format tokens from the legacy shared column
    op.execute(
        "UPDATE push_subscriptions SET expo_push_token = player_id "
        "WHERE player_id LIKE 'ExponentPushToken[%' AND expo_push_token IS NULL"
    )
    op.add_column(
        "emergency_sessions", sa.Column("hospital", sa.String(256), nullable=True)
    )
    op.add_column(
        "emergency_sessions", sa.Column("ended_reason", sa.String(32), nullable=True)
    )
    op.create_index(
        "ix_sessions_driver_status_started",
        "emergency_sessions",
        ["driver_id", "status", "started_at"],
    )
    op.create_index(
        "ix_gps_session_recorded", "gps_points", ["session_id", "recorded_at"]
    )
    op.create_index(
        "ix_detections_junction_detected",
        "detections",
        ["junction_id", "detected_at"],
    )


def downgrade():
    op.drop_index("ix_detections_junction_detected", table_name="detections")
    op.drop_index("ix_gps_session_recorded", table_name="gps_points")
    op.drop_index("ix_sessions_driver_status_started", table_name="emergency_sessions")
    op.drop_column("emergency_sessions", "ended_reason")
    op.drop_column("emergency_sessions", "hospital")
    op.drop_index("ix_push_expo_token", table_name="push_subscriptions")
    op.drop_column("push_subscriptions", "expo_push_token")
    op.drop_table("detections")
    op.drop_table("driver_profiles")
