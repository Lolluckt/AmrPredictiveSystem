"""Logistics-mission endpoints.

A mission is a transport job placed by an operator (or by the MES).  Its
lifecycle is:

    queued → assigned → in_transit → (loading/unloading) → completed
                                  ↘ failed / cancelled

The router persists state changes, writes audit rows, broadcasts events
and — when a robot is assigned — pushes a mission notification to the
controller via MQTT so the simulator picks up the task on its next loop.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deps import require_permission
from ..core.roles import Permission
from ..db import get_session
from ..models.mission import Mission
from ..models.robot import Robot
from ..models.user import User
from ..schemas.mission import (
    MissionCreate, MissionOut, MissionUpdate, VALID_PRIORITIES, VALID_STATUSES,
)
from ..services.audit import record as audit
from ..services.event_bus import bus
from ..services.mqtt_publisher import publish_mission_assignment

router = APIRouter(prefix="/api/missions", tags=["missions"])


def _validate(payload: MissionCreate | MissionUpdate) -> None:
    if payload.priority and payload.priority not in VALID_PRIORITIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"priority must be one of {sorted(VALID_PRIORITIES)}")
    if isinstance(payload, MissionUpdate) and payload.status\
            and payload.status not in VALID_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"status must be one of {sorted(VALID_STATUSES)}")


def _emit(action: str, m: Mission) -> None:
    bus.publish("mission", action, entity_id=m.id, robot_id=m.robot_id,
                data=MissionOut.model_validate(m).model_dump(mode="json"))


@router.get("", response_model=list[MissionOut])
async def list_missions(
    status_filter: Optional[str] = Query(None, alias="status"),
    robot_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.MISSIONS_VIEW)),
) -> list[Mission]:
    q = select(Mission).order_by(Mission.created_at.desc())
    if status_filter:
        q = q.where(Mission.status == status_filter)
    if robot_id:
        q = q.where(Mission.robot_id == robot_id)
    return list((await db.execute(q)).scalars())


@router.get("/{mission_id}", response_model=MissionOut)
async def get_mission(
    mission_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.MISSIONS_VIEW)),
) -> Mission:
    m = await db.get(Mission, mission_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return m


@router.post("", response_model=MissionOut, status_code=status.HTTP_201_CREATED)
async def create_mission(
    payload: MissionCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.MISSIONS_CREATE)),
) -> Mission:
    _validate(payload)
    m = Mission(**payload.model_dump(exclude_none=True), created_by=user.id)
    if m.robot_id:
        m.status = "assigned"
    db.add(m)
    await audit(db, user_id=user.id, action="mission.create",
                entity_type="mission", entity_id=m.id,
                details=payload.model_dump(exclude_none=True))
    await db.commit()
    await db.refresh(m)

    if m.robot_id:
        robot = await db.get(Robot, m.robot_id)
        if robot:
            publish_mission_assignment(robot.mqtt_client_id, str(m.id),
                                       action="assigned",
                                       extra={"priority": m.priority,
                                              "payload_type": m.payload_type})
    _emit("create", m)
    return m


@router.patch("/{mission_id}", response_model=MissionOut)
async def update_mission(
    mission_id: UUID,
    payload: MissionUpdate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.MISSIONS_CREATE)),
) -> Mission:
    _validate(payload)
    m = await db.get(Mission, mission_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    changes = payload.model_dump(exclude_none=True)
    prev_status = m.status
    prev_robot = m.robot_id
    for k, v in changes.items():
        setattr(m, k, v)


    if payload.status == "in_transit" and not m.started_at:
        m.started_at = datetime.now(timezone.utc)
    if payload.status in ("completed", "failed", "cancelled") and not m.completed_at:
        m.completed_at = datetime.now(timezone.utc)

    await audit(db, user_id=user.id, action="mission.update",
                entity_type="mission", entity_id=m.id,
                details={"changes": changes, "prev_status": prev_status})
    await db.commit()
    await db.refresh(m)


    if m.robot_id and m.robot_id != prev_robot:
        robot = await db.get(Robot, m.robot_id)
        if robot:
            publish_mission_assignment(robot.mqtt_client_id, str(m.id),
                                       action="assigned",
                                       extra={"priority": m.priority})
    _emit("update", m)
    return m


@router.post("/{mission_id}/cancel", response_model=MissionOut)
async def cancel_mission(
    mission_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.MISSIONS_CANCEL)),
) -> Mission:
    m = await db.get(Mission, mission_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if m.status in ("completed", "cancelled"):
        return m
    m.status = "cancelled"
    m.completed_at = datetime.now(timezone.utc)
    await audit(db, user_id=user.id, action="mission.cancel",
                entity_type="mission", entity_id=m.id, details={"by": str(user.id)})
    await db.commit()
    await db.refresh(m)

    if m.robot_id:
        robot = await db.get(Robot, m.robot_id)
        if robot:
            publish_mission_assignment(robot.mqtt_client_id, str(m.id),
                                       action="cancelled")
    _emit("cancel", m)
    return m
