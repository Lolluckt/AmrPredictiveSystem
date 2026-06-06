"""Robot fleet registry + components."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Robot(Base):
    __tablename__ = "robots"

    id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    line_id:        Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("production_lines.id", ondelete="SET NULL"), index=True)
    code:           Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    serial_number:  Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    model:          Mapped[str] = mapped_column(String(60), default="AMR-100X")
    mqtt_client_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    status:         Mapped[str] = mapped_column(String(30), default="idle", index=True)

    last_x:             Mapped[float | None] = mapped_column(Float)
    last_y:             Mapped[float | None] = mapped_column(Float)
    last_heading_deg:   Mapped[float | None] = mapped_column(Float)
    last_zone:          Mapped[str | None] = mapped_column(String(60))
    last_seen_at:       Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_odometry_m:   Mapped[float] = mapped_column(Float, default=0.0)
    total_missions:     Mapped[int] = mapped_column(Integer, default=0)
    firmware_version:   Mapped[str] = mapped_column(String(30), default="v2.4.1")

    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    components: Mapped[list["RobotComponent"]] = relationship(back_populates="robot", cascade="all, delete-orphan")


class RobotComponent(Base):
    __tablename__ = "robot_components"
    id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    robot_id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("robots.id", ondelete="CASCADE"), nullable=False, index=True)
    category:     Mapped[str] = mapped_column(String(30), nullable=False)
    name:         Mapped[str] = mapped_column(String(200), nullable=False)
    position_label: Mapped[str | None] = mapped_column(String(60))
    part_number:  Mapped[str | None] = mapped_column(String(60))
    current_soh_pct: Mapped[float | None] = mapped_column(Float)
    expected_life_hours: Mapped[int | None] = mapped_column(Integer)
    current_hours:  Mapped[int] = mapped_column(Integer, default=0)

    robot: Mapped[Robot] = relationship(back_populates="components")
