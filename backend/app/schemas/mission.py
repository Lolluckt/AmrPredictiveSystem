from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
VALID_STATUSES = {
    "queued", "assigned", "in_transit", "loading",
    "unloading", "completed", "failed", "cancelled",
}


class MissionCreate(BaseModel):
    robot_id: Optional[UUID] = None
    origin_zone_id: Optional[UUID] = None
    destination_zone_id: Optional[UUID] = None
    payload_type: Optional[str] = None
    payload_weight_kg: Optional[float] = Field(default=None, ge=0, le=500)
    priority: str = "medium"
    mes_order_id: Optional[str] = None
    notes: Optional[str] = None


class MissionUpdate(BaseModel):
    robot_id: Optional[UUID] = None
    origin_zone_id: Optional[UUID] = None
    destination_zone_id: Optional[UUID] = None
    payload_type: Optional[str] = None
    payload_weight_kg: Optional[float] = Field(default=None, ge=0, le=500)
    status: Optional[str] = None
    priority: Optional[str] = None
    mes_order_id: Optional[str] = None
    notes: Optional[str] = None


class MissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    robot_id: Optional[UUID]
    origin_zone_id: Optional[UUID]
    destination_zone_id: Optional[UUID]
    payload_type: Optional[str]
    payload_weight_kg: Optional[float]
    status: str
    priority: str
    mes_order_id: Optional[str]
    notes: Optional[str]
    created_by: Optional[UUID]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
