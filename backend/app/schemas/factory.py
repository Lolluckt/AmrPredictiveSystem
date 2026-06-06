from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ChargingStationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    x_position: float
    y_position: float
    max_power_w: int
    is_occupied: bool


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    line_id: UUID
    name: str
    zone_type: str
    color_hex: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class ProductionLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    factory_id: UUID
    name: str
    code: str
    description: Optional[str]


class FactoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    code: str
    city: Optional[str]


class FactoryLayoutOut(BaseModel):
    """Combined snapshot for the dashboard map: factories + lines + zones + chargers."""
    factories: list[FactoryOut]
    lines: list[ProductionLineOut]
    zones: list[ZoneOut]
    chargers: list[ChargingStationOut]
