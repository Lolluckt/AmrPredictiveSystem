"""Logistics missions (transport jobs) executed by AMRs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Mission(Base):
    __tablename__ = "missions"

    id:        Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    robot_id:  Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("robots.id", ondelete="SET NULL"), index=True)
    line_id:   Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("production_lines.id", ondelete="SET NULL"))
    origin_zone_id:      Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("workshop_zones.id", ondelete="SET NULL"))
    destination_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("workshop_zones.id", ondelete="SET NULL"))

    payload_type:  Mapped[str | None] = mapped_column(String(60))
    payload_weight_kg: Mapped[float | None] = mapped_column(Float)
    status:        Mapped[str] = mapped_column(String(20), default="queued", index=True)
    priority:      Mapped[str] = mapped_column(String(10), default="medium")
    mes_order_id:  Mapped[str | None] = mapped_column(String(60))
    notes:         Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    started_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
