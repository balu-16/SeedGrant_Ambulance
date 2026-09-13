import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(16), default="DRIVER", index=True
    )  # ADMIN | HOSPITAL | POLICE | DRIVER
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    refresh_version: Mapped[int] = mapped_column(
        default=0
    )  # bumped on logout; invalidates old refresh tokens
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ambulances: Mapped[list["Ambulance"]] = relationship("Ambulance", back_populates="driver")


class Ambulance(Base):
    __tablename__ = "ambulances"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    driver: Mapped["User | None"] = relationship("User", back_populates="ambulances")
    __table_args__ = (
        # a driver may be assigned to at most one ambulance (NULL rows exempt)
        Index(
            "uq_ambulances_driver",
            "driver_id",
            unique=True,
            postgresql_where=text("driver_id IS NOT NULL"),
            sqlite_where=text("driver_id IS NOT NULL"),
        ),
    )
