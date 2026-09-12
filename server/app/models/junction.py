import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Junction(Base):
    __tablename__ = "junctions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[float] = mapped_column(Float, default=500.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approaches: Mapped[list["Approach"]] = relationship(
        "Approach", back_populates="junction", cascade="all, delete-orphan"
    )


class Approach(Base):
    __tablename__ = "approaches"
    __table_args__ = (
        UniqueConstraint("junction_id", "direction", name="uq_approach_junction_dir"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    junction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("junctions.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[str] = mapped_column(String(8), index=True)  # NORTH|SOUTH|EAST|WEST
    heading_min: Mapped[float] = mapped_column(Float)
    heading_max: Mapped[float] = mapped_column(Float)
    entry_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta_data: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    junction: Mapped["Junction"] = relationship("Junction", back_populates="approaches")
