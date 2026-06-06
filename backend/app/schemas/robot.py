from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RobotListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    model: str
    status: str
    last_x: Optional[float]
    last_y: Optional[float]
    last_zone: Optional[str]
    last_seen_at: Optional[datetime]
    firmware_version: str


class RobotComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    category: str
    name: str
    position_label: Optional[str]
    part_number: Optional[str]
    current_soh_pct: Optional[float]
    expected_life_hours: Optional[int]
    current_hours: int


class RobotOut(RobotListItem):
    serial_number: str
    mqtt_client_id: str
    total_odometry_m: float
    total_missions: int
    components: list[RobotComponentOut]


class RobotCreate(BaseModel):
    code: str = Field(min_length=3, max_length=30)
    serial_number: str
    model: str = "AMR-100X"
    mqtt_client_id: str
    line_id: Optional[UUID] = None


class RobotUpdate(BaseModel):
    status: Optional[str] = None
    firmware_version: Optional[str] = None


class RobotCommandIn(BaseModel):
    command: str
    params: dict[str, Any] = Field(default_factory=dict)
