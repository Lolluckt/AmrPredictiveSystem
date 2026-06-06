from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AlertRuleIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    parameter: str
    operator: str = ">"
    threshold: float
    severity: str = "warning"
    description: Optional[str] = None
    is_enabled: bool = True


    mode: str = Field(default="static", pattern="^(static|adaptive)$")
    window_minutes: int = Field(default=30, ge=1, le=720)
    k_sigma: float = Field(default=3.0, ge=0.5, le=10.0)


class AlertRuleOut(AlertRuleIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


class AnomalyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    robot_id: UUID
    rule_id: Optional[UUID]
    severity: str
    parameter: str
    value: float
    threshold: float
    message: str
    detected_at: datetime
    acknowledged_at: Optional[datetime]
    acknowledged_by: Optional[UUID]
    acknowledged_by_name: Optional[str] = None
    resolved_at: Optional[datetime]
