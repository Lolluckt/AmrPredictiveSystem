from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class ComponentHealth(BaseModel):
    component_id: UUID
    category: str
    name: str
    health_score: float
    soh_pct: Optional[float]
    degradation_trend: Literal["stable", "improving", "degrading", "critical"]
    notes: str


class RulPrediction(BaseModel):
    robot_id: UUID
    component_id: UUID
    component_name: str
    predicted_rul_hours: float
    confidence: float
    recommendation: str
    predicted_at: datetime

    model: Literal["heuristic", "linear_regression"] = "heuristic"
    r2_score: Optional[float] = None
    soh_slope_pct_per_day: Optional[float] = None
    days_to_replacement: Optional[float] = None
    replacement_threshold_pct: Optional[float] = None


class SohForecastPoint(BaseModel):
    """Точка на прогнозній лінії (predicted SoH у час t)."""
    t: datetime
    soh_pct: float
    is_forecast: bool


class SohForecast(BaseModel):
    """Серії для побудови графіка 'SoH у часі + регресійна лінія + поріг'."""
    robot_id: UUID
    component_id: UUID
    history: list[SohForecastPoint]
    forecast: list[SohForecastPoint]
    intercept_pct: float
    slope_pct_per_day: float
    r2_score: float
    replacement_threshold_pct: float
    days_to_replacement: Optional[float]
    n_samples: int
