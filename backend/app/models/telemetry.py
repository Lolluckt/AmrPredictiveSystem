"""Time-series telemetry snapshots — one row per MQTT message batch.

For the production stack this table is downsampled from InfluxDB; inside the
prototype, the MQTT ingester writes directly to PostgreSQL.  An index on
(robot_id, recorded_at DESC) keeps recent-window queries cheap.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class TelemetrySnapshot(Base):
    __tablename__ = "telemetry_snapshots"

    id:            Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    robot_id:      Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("robots.id", ondelete="CASCADE"), nullable=False)
    recorded_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


    pos_x:  Mapped[float | None] = mapped_column(Float)
    pos_y:  Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    zone:   Mapped[str | None] = mapped_column(String(60))


    battery_soc:     Mapped[float | None] = mapped_column(Float)
    battery_soh:     Mapped[float | None] = mapped_column(Float)
    battery_voltage: Mapped[float | None] = mapped_column(Float)
    battery_current: Mapped[float | None] = mapped_column(Float)
    battery_temp:    Mapped[float | None] = mapped_column(Float)
    battery_internal_r: Mapped[float | None] = mapped_column(Float)


    left_motor_temp:   Mapped[float | None] = mapped_column(Float)
    right_motor_temp:  Mapped[float | None] = mapped_column(Float)
    left_motor_vib:    Mapped[float | None] = mapped_column(Float)
    right_motor_vib:   Mapped[float | None] = mapped_column(Float)
    left_motor_eff:    Mapped[float | None] = mapped_column(Float)
    right_motor_eff:   Mapped[float | None] = mapped_column(Float)


    odometry_m:  Mapped[float | None] = mapped_column(Float)
    state:       Mapped[str | None] = mapped_column(String(30))
    mission_step: Mapped[int | None] = mapped_column(Integer)


    raw: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_snapshots_robot_time", "robot_id", "recorded_at"),
    )
