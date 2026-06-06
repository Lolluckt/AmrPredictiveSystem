from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TelemetryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    robot_id: UUID
    recorded_at: datetime
    pos_x: Optional[float]
    pos_y: Optional[float]
    heading_deg: Optional[float]
    zone: Optional[str]
    battery_soc: Optional[float]
    battery_soh: Optional[float]
    battery_voltage: Optional[float]
    battery_current: Optional[float]
    battery_temp: Optional[float]
    left_motor_temp: Optional[float]
    right_motor_temp: Optional[float]
    left_motor_vib: Optional[float]
    right_motor_vib: Optional[float]
    odometry_m: Optional[float]
    state: Optional[str]
    raw: Optional[dict[str, Any]] = None


class TelemetrySeriesPoint(BaseModel):
    t: datetime
    value: float


class TelemetryIngestIn(BaseModel):
    """Payload accepted by POST /api/telemetry/ingest (fallback HTTP ingest
    when MQTT isn't used). Fields mirror TelemetrySnapshot columns plus raw."""
    robot_code: str
    recorded_at: Optional[datetime] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    heading_deg: Optional[float] = None
    zone: Optional[str] = None
    battery_soc: Optional[float] = None
    battery_soh: Optional[float] = None
    battery_voltage: Optional[float] = None
    battery_current: Optional[float] = None
    battery_temp: Optional[float] = None
    left_motor_temp: Optional[float] = None
    right_motor_temp: Optional[float] = None
    left_motor_vib: Optional[float] = None
    right_motor_vib: Optional[float] = None
    left_motor_eff: Optional[float] = None
    right_motor_eff: Optional[float] = None
    odometry_m: Optional[float] = None
    state: Optional[str] = None
    raw: Optional[dict[str, Any]] = None
