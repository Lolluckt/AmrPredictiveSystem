"""Alert rules + raised anomaly events."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlertRule(Base):
    __tablename__ = "alert_rules"
    id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parameter: Mapped[str] = mapped_column(String(80), nullable=False)
    operator:  Mapped[str] = mapped_column(String(5), default=">")
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    severity:  Mapped[str] = mapped_column(String(20), default="warning")
    description: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


    mode: Mapped[str] = mapped_column(String(20), default="static", nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    k_sigma: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"
    id:        Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    robot_id:  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("robots.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id:   Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="SET NULL"))
    severity:  Mapped[str] = mapped_column(String(20), default="warning")
    parameter: Mapped[str] = mapped_column(String(80), nullable=False)
    value:     Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    message:   Mapped[str]   = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at:     Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
