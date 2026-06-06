"""Factory layout: factories, production lines, workshop zones, chargers.

The frontend uses ``/api/factory/layout`` to draw the live shop-floor map
in one round-trip.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deps import current_user
from ..db import get_session
from ..models.factory import ChargingStation, Factory, ProductionLine, WorkshopZone
from ..models.user import User
from ..schemas.factory import (
    ChargingStationOut, FactoryLayoutOut, FactoryOut, ProductionLineOut, ZoneOut,
)

router = APIRouter(prefix="/api/factory", tags=["factory"])


@router.get("/factories", response_model=list[FactoryOut])
async def list_factories(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
) -> list[Factory]:
    return list((await db.execute(select(Factory).order_by(Factory.code))).scalars())


@router.get("/lines", response_model=list[ProductionLineOut])
async def list_lines(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
) -> list[ProductionLine]:
    return list((await db.execute(select(ProductionLine).order_by(ProductionLine.code))).scalars())


@router.get("/zones", response_model=list[ZoneOut])
async def list_zones(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
) -> list[WorkshopZone]:
    return list((await db.execute(select(WorkshopZone).order_by(WorkshopZone.name))).scalars())


@router.get("/chargers", response_model=list[ChargingStationOut])
async def list_chargers(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
) -> list[ChargingStation]:
    return list((await db.execute(select(ChargingStation).order_by(ChargingStation.code))).scalars())


@router.get("/layout", response_model=FactoryLayoutOut)
async def layout(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
) -> FactoryLayoutOut:
    factories = list((await db.execute(select(Factory).order_by(Factory.code))).scalars())
    lines    = list((await db.execute(select(ProductionLine).order_by(ProductionLine.code))).scalars())
    zones    = list((await db.execute(select(WorkshopZone).order_by(WorkshopZone.name))).scalars())
    chargers = list((await db.execute(select(ChargingStation).order_by(ChargingStation.code))).scalars())
    return FactoryLayoutOut(
        factories=[FactoryOut.model_validate(f) for f in factories],
        lines=[ProductionLineOut.model_validate(l) for l in lines],
        zones=[ZoneOut.model_validate(z) for z in zones],
        chargers=[ChargingStationOut.model_validate(c) for c in chargers],
    )
