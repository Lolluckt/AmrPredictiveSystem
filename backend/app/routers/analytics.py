"""Аналітика парку: KPI-вкладка дашборду."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deps import require_permission
from ..core.roles import Permission
from ..db import get_session
from ..models.user import User
from ..services.analytics import kpi_snapshot

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/kpi")
async def get_kpi(
    period: str = Query("24h", description="Готовий період: 1h | 24h | 7d | 30d"),
    from_: Optional[datetime] = Query(None, alias="from"),
    to:    Optional[datetime] = None,
    robot_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.PREDICTIVE_VIEW)),
) -> dict:
    """KPI-агрегат за період.  Якщо ``from``/``to`` не вказані — використовується
    готовий ``period`` (1h, 24h, 7d, 30d)."""
    if not from_:
        now = datetime.now(timezone.utc)
        delta_map = {"1h": timedelta(hours=1),
                     "24h": timedelta(hours=24),
                     "7d":  timedelta(days=7),
                     "30d": timedelta(days=30)}
        delta = delta_map.get(period, timedelta(hours=24))
        from_ = now - delta
        to = to or now
    return await kpi_snapshot(db, period_from=from_, period_to=to, robot_id=robot_id)
