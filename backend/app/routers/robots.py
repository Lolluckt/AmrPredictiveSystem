"""Fleet registry endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.deps import require_permission
from ..core.roles import Permission
from ..db import get_session
from ..models.robot import Robot
from ..models.user import User
from ..schemas.robot import (
    RobotCommandIn, RobotCreate, RobotListItem, RobotOut, RobotUpdate,
)
from ..services.audit import record as audit
from ..services.dock_allocator import allocate as allocate_dock
from ..services.event_bus import bus
from ..services.mqtt_publisher import publish_command

router = APIRouter(prefix="/api/robots", tags=["robots"])


ALLOWED_COMMANDS = {
    "stop", "resume", "return_to_charge", "emergency_stop",
    "inject_fault", "clear_fault", "mission",
}


@router.get("", response_model=list[RobotListItem])
async def list_robots(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.ROBOTS_VIEW)),
) -> list[Robot]:
    res = await db.execute(select(Robot).order_by(Robot.code))
    return list(res.scalars())


@router.post("", response_model=RobotOut, status_code=status.HTTP_201_CREATED)
async def create_robot(
    payload: RobotCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.ROBOTS_EDIT)),
) -> Robot:
    robot = Robot(**payload.model_dump())
    db.add(robot)
    await audit(db, user_id=user.id, action="robot.create",
                entity_type="robot", entity_id=robot.id,
                details={"code": payload.code})
    await db.commit()

    q = (select(Robot).where(Robot.id == robot.id)
         .options(selectinload(Robot.components)))
    robot = (await db.execute(q)).scalar_one()
    bus.publish("robot", "create", entity_id=robot.id, robot_id=robot.id,
                data={"id": str(robot.id), "code": robot.code, "status": robot.status})
    return robot


@router.get("/{robot_id}", response_model=RobotOut)
async def get_robot(
    robot_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.ROBOTS_VIEW)),
) -> Robot:
    q = select(Robot).where(Robot.id == robot_id).options(selectinload(Robot.components))
    res = await db.execute(q)
    robot = res.scalar_one_or_none()
    if not robot:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Робота не знайдено")
    return robot


@router.patch("/{robot_id}", response_model=RobotOut)
async def update_robot(
    robot_id: UUID,
    payload: RobotUpdate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.ROBOTS_EDIT)),
) -> Robot:
    q = select(Robot).where(Robot.id == robot_id).options(selectinload(Robot.components))
    robot = (await db.execute(q)).scalar_one_or_none()
    if not robot:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    changes = payload.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(robot, k, v)
    await audit(db, user_id=user.id, action="robot.update",
                entity_type="robot", entity_id=robot.id, details=changes)
    await db.commit()
    await db.refresh(robot)
    bus.publish("robot", "update", entity_id=robot.id, robot_id=robot.id,
                data={"id": str(robot.id), "code": robot.code, "status": robot.status})
    return robot


@router.post("/{robot_id}/command")
async def send_command(
    robot_id: UUID,
    payload: RobotCommandIn,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.ROBOTS_COMMAND)),
) -> dict:
    if payload.command not in ALLOWED_COMMANDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Невідома команда '{payload.command}'")
    robot = await db.get(Robot, robot_id)
    if not robot:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Робота не знайдено")


    dock_extra: dict = {}
    if payload.command == "return_to_charge":
        try:
            dock = await allocate_dock(db, robot.id)
        except Exception as exc:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                f"Помилка розподілу дока: {exc}",
            )
        if dock is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Усі зарядні станції зайняті — поставте робота в чергу або зачекайте.",
            )
        dock_extra = {"dock_node": dock.node_name, "dock_code": dock.code}

    body = {"command": payload.command, **payload.params, **dock_extra,
            "issued_by": str(user.id),
            "issued_at": datetime.now(timezone.utc).isoformat()}
    delivered = publish_command(robot.mqtt_client_id, body)

    await audit(db, user_id=user.id, action="robot.command",
                entity_type="robot", entity_id=robot.id,
                details={"command": payload.command, "params": payload.params,
                         "delivered": delivered})
    await db.commit()

    bus.publish(
        "robot", "command",
        robot_id=robot.id, entity_id=robot.id,
        data={"robot_id": str(robot.id), "robot_code": robot.code,
              "command": payload.command, "params": payload.params,
              "delivered": delivered, "issued_by": str(user.id)},
    )

    if not delivered:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Команду не доставлено: MQTT недоступний. Робот: {robot.code}",
        )
    result: dict = {"delivered": True, "robot": robot.code,
                    "command": payload.command, "params": payload.params}
    if dock_extra:
        result["assigned_dock"] = dock_extra["dock_code"]
    return result
