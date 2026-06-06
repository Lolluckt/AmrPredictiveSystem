"""Predictive-maintenance endpoints: component health + RUL + fleet summary."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deps import require_permission
from ..core.roles import Permission
from ..db import get_session
from ..models.user import User
from ..schemas.predictive import ComponentHealth, RulPrediction, SohForecast
from ..services.predictive import (
    component_health, fleet_health_summary, rul_estimates, soh_forecast,
)

router = APIRouter(prefix="/api/predictive", tags=["predictive"])


@router.get("/robots/{robot_id}/health", response_model=list[ComponentHealth])
async def robot_health(
    robot_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.PREDICTIVE_VIEW)),
) -> list[ComponentHealth]:
    return await component_health(db, robot_id)


@router.get("/robots/{robot_id}/rul", response_model=list[RulPrediction])
async def robot_rul(
    robot_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.PREDICTIVE_VIEW)),
) -> list[RulPrediction]:
    return await rul_estimates(db, robot_id)


@router.get("/fleet")
async def fleet(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.PREDICTIVE_VIEW)),
) -> list[dict]:
    return [{"robot_id": str(rid), "code": code, "health_score": score}
            for rid, code, score in await fleet_health_summary(db)]


@router.get("/robots/{robot_id}/soh-forecast", response_model=SohForecast)
async def soh_forecast_endpoint(
    robot_id: UUID,
    component_id: Optional[UUID] = None,
    threshold_pct: float = Query(70.0, ge=10.0, le=100.0,
                                  description="Поріг SoH, при якому потрібна заміна"),
    horizon_days: int = Query(180, ge=7, le=730,
                               description="На скільки днів вперед екстраполювати"),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.PREDICTIVE_VIEW)),
) -> SohForecast:
    """Серії {історія + регресійна екстраполяція} SoH для побудови графіка.

    Якщо точок недостатньо або тренд незначущий — повертає 404 з
    зрозумілим повідомленням замість "пустого" графіка.
    """
    fc = await soh_forecast(db, robot_id, component_id=component_id,
                            threshold_pct=threshold_pct, horizon_days=horizon_days)
    if fc is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Недостатньо даних для регресії або SoH-тренд незначущий "
            "(R²<0.25). Подайте більше телеметрії та спробуйте знову.",
        )
    return fc
