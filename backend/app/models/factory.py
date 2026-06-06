"""Factory layout: factory → production_line → zones + charging stations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Factory(Base):
    __tablename__ = "factories"
    id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))
    lines: Mapped[list["ProductionLine"]] = relationship(back_populates="factory", cascade="all, delete-orphan")


class ProductionLine(Base):
    __tablename__ = "production_lines"
    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    factory: Mapped[Factory] = relationship(back_populates="lines")
    zones:   Mapped[list["WorkshopZone"]] = relationship(back_populates="line", cascade="all, delete-orphan")


class WorkshopZone(Base):
    __tablename__ = "workshop_zones"
    id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    line_id:  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("production_lines.id", ondelete="CASCADE"), nullable=False, index=True)
    name:     Mapped[str] = mapped_column(String(200), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(40), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(9), default="#6B7280", nullable=False)
    x_min: Mapped[float] = mapped_column(Float, nullable=False)
    y_min: Mapped[float] = mapped_column(Float, nullable=False)
    x_max: Mapped[float] = mapped_column(Float, nullable=False)
    y_max: Mapped[float] = mapped_column(Float, nullable=False)

    line:    Mapped[ProductionLine] = relationship(back_populates="zones")
    chargers: Mapped[list["ChargingStation"]] = relationship(back_populates="zone", cascade="all, delete-orphan")


class ChargingStation(Base):
    __tablename__ = "charging_stations"
    id:      Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workshop_zones.id", ondelete="CASCADE"), nullable=False, index=True)
    code:    Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    x_position: Mapped[float] = mapped_column(Float, nullable=False)
    y_position: Mapped[float] = mapped_column(Float, nullable=False)
    max_power_w: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    is_occupied: Mapped[bool] = mapped_column(default=False)

    zone: Mapped[WorkshopZone] = relationship(back_populates="chargers")
