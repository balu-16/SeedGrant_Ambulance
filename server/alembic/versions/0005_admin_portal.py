"""admin portal: hospitals, police_assignments, hospital FKs on users/ambulances

requires `alembic upgrade head` before deploy
"""
# ruff: noqa: E402, I001 — alembic revision vars precede imports by convention
revision = "0005_admin_portal"
down_revision = "0004_command_retry_count"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade():
    op.create_table(
        "hospitals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column(
        "users",
        sa.Column(
            "hospital_id", UUID(as_uuid=True), sa.ForeignKey("hospitals.id"), nullable=True
        ),
    )
    op.create_index("ix_users_hospital_id", "users", ["hospital_id"])
    op.add_column(
        "ambulances",
        sa.Column(
            "hospital_id", UUID(as_uuid=True), sa.ForeignKey("hospitals.id"), nullable=True
        ),
    )
    op.create_index("ix_ambulances_hospital_id", "ambulances", ["hospital_id"])
    op.create_table(
        "police_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column(
            "junction_id",
            UUID(as_uuid=True),
            sa.ForeignKey("junctions.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "junction_id", name="uq_police_assignment_user_junction"),
    )


def downgrade():
    op.drop_table("police_assignments")
    op.drop_index("ix_ambulances_hospital_id", table_name="ambulances")
    op.drop_column("ambulances", "hospital_id")
    op.drop_index("ix_users_hospital_id", table_name="users")
    op.drop_column("users", "hospital_id")
    op.drop_table("hospitals")
