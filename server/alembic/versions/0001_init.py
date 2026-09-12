"""initial tables"""
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


def upgrade():
    op.create_table("users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, index=True),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("role", sa.String(16), index=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("ambulances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("vehicle_no", sa.String(32), unique=True, index=True),
        sa.Column("driver_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("junctions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), index=True),
        sa.Column("latitude", sa.Float()), sa.Column("longitude", sa.Float()),
        sa.Column("radius_m", sa.Float(), default=500.0),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("approaches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("junction_id", UUID(as_uuid=True), sa.ForeignKey("junctions.id", ondelete="CASCADE"), index=True),
        sa.Column("direction", sa.String(8), index=True),
        sa.Column("heading_min", sa.Float()), sa.Column("heading_max", sa.Float()),
        sa.Column("entry_lat", sa.Float(), nullable=True), sa.Column("entry_lon", sa.Float(), nullable=True),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.UniqueConstraint("junction_id", "direction", name="uq_approach_junction_dir"))
    op.create_table("devices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("junction_id", UUID(as_uuid=True), sa.ForeignKey("junctions.id"), unique=True, index=True),
        sa.Column("name", sa.String(128)),
        sa.Column("api_key_hash", sa.String(128), unique=True, index=True),
        sa.Column("is_online", sa.Boolean(), default=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("telemetry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("junction_id", UUID(as_uuid=True), sa.ForeignKey("junctions.id"), index=True),
        sa.Column("device_id", UUID(as_uuid=True), sa.ForeignKey("devices.id"), index=True),
        sa.Column("payload", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True))
    op.create_table("heartbeats",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", UUID(as_uuid=True), sa.ForeignKey("devices.id"), index=True),
        sa.Column("payload", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True))
    op.create_table("emergency_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ambulance_id", UUID(as_uuid=True), sa.ForeignKey("ambulances.id"), index=True),
        sa.Column("driver_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), index=True),
        sa.Column("status", sa.String(32), index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_gps_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table("gps_points",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("emergency_sessions.id", ondelete="CASCADE"), index=True),
        sa.Column("latitude", sa.Float()), sa.Column("longitude", sa.Float()),
        sa.Column("accuracy", sa.Float(), nullable=True), sa.Column("speed", sa.Float(), nullable=True),
        sa.Column("heading", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True))
    op.create_table("emergency_commands",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("emergency_sessions.id"), index=True),
        sa.Column("junction_id", UUID(as_uuid=True), sa.ForeignKey("junctions.id"), index=True),
        sa.Column("approach", sa.String(8)),
        sa.Column("command_type", sa.String(32), index=True),
        sa.Column("status", sa.String(16), index=True),
        sa.Column("correlation_id", sa.String(64), unique=True, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("ack_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("actor", sa.String(255), default=""),
        sa.Column("action", sa.String(128), index=True),
        sa.Column("entity", sa.String(128), default=""),
        sa.Column("detail", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True))


def downgrade():
    for t in ("audit_logs", "emergency_commands", "gps_points", "emergency_sessions", "heartbeats", "telemetry", "devices", "approaches", "junctions", "ambulances", "users"):
        op.drop_table(t)
