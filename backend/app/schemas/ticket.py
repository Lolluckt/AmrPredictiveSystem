from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TicketBase(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: Optional[str] = None
    maintenance_type: str = "predictive"
    priority: str = "medium"
    estimated_hours: Optional[float] = None


class TicketCreate(TicketBase):
    robot_id: UUID
    component_id: Optional[UUID] = None
    anomaly_id: Optional[UUID] = None
    assigned_to: Optional[UUID] = None
    sla_deadline: Optional[datetime] = None


class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[UUID] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    sla_deadline: Optional[datetime] = None


class TicketCommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class TicketCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: Optional[UUID]
    body: str
    created_at: datetime


class TicketOut(TicketBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    robot_id: UUID
    component_id: Optional[UUID]
    anomaly_id: Optional[UUID]
    status: str
    created_by: Optional[UUID]
    assigned_to: Optional[UUID]
    actual_hours: Optional[float]
    sla_deadline: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    comments: list[TicketCommentOut] = []
