"""Авто-створення CMMS-заявки з аномалії.

Поведінка:
    * ``severity in {"critical", "emergency"}`` → одразу створити Ticket
      (``maintenance_type="predictive"`` для critical, ``"emergency"`` для emergency).
    * ``severity in {"warning", "info"}`` → нічого не робимо автоматично;
      оператор може створити заявку вручну через endpoint
      ``POST /api/anomalies/{id}/ticket``.

Захист від спаму:
    * Не створюємо новий тікет, якщо для цього робота вже є **відкритий**
      тікет із прив'язкою до того ж ``parameter``.  Замість цього додаємо
      коментар "ескалація: повторна аномалія …" до існуючого тікета.

Це і виправляє той самий вибух тікетів, що його сесія попереджала в
попередньому commit-і на anomaly engine (cooldown).  Cooldown спрацьовує
на рівні подій (event flooding); цей dedup — на рівні заявок.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.alert import AnomalyEvent
from ..models.robot import Robot, RobotComponent
from ..models.ticket import Ticket, TicketComment
from ..models.user import User
from ..schemas.ticket import TicketOut
from .event_bus import bus

log = logging.getLogger("auto_ticket")


PARAM_TO_COMPONENT_HINT = {
    "battery_soc":      ("battery", None),
    "battery_soh":      ("battery", None),
    "battery_temp":     ("battery", None),
    "battery_voltage":  ("battery", None),
    "left_motor_temp":  ("motor",   "left_wheel"),
    "right_motor_temp": ("motor",   "right_wheel"),
    "left_motor_vib":   ("motor",   "left_wheel"),
    "right_motor_vib":  ("motor",   "right_wheel"),
}


PARAM_TITLE = {
    "battery_soc":      "Низький заряд батареї",
    "battery_soh":      "Деградація батареї",
    "battery_temp":     "Перегрів батареї",
    "battery_voltage":  "Аномальна напруга батареї",
    "left_motor_temp":  "Перегрів лівого тягового двигуна",
    "right_motor_temp": "Перегрів правого тягового двигуна",
    "left_motor_vib":   "Підвищена вібрація лівого двигуна",
    "right_motor_vib":  "Підвищена вібрація правого двигуна",
}


SEVERITY_MAP = {
    "emergency": ("emergency",  "urgent"),
    "critical":  ("predictive", "high"),
    "warning":   ("predictive", "medium"),
    "info":      ("predictive", "low"),
}

OPEN_STATUSES = ("open", "assigned", "in_progress", "waiting_parts")


def _emit(action: str, ticket: Ticket) -> None:
    bus.publish("ticket", action, entity_id=ticket.id, robot_id=ticket.robot_id,
                data=TicketOut.model_validate(ticket).model_dump(mode="json"))


async def _find_component(db: AsyncSession, robot_id: UUID,
                          parameter: str) -> Optional[RobotComponent]:
    hint = PARAM_TO_COMPONENT_HINT.get(parameter)
    if not hint:
        return None
    category, pos = hint
    q = select(RobotComponent).where(RobotComponent.robot_id == robot_id,
                                     RobotComponent.category == category)
    if pos:
        q = q.where(RobotComponent.position_label == pos)
    return (await db.execute(q)).scalars().first()


async def _open_ticket_for_param(db: AsyncSession, robot_id: UUID,
                                 parameter: str) -> Optional[Ticket]:
    """Чи є вже відкритий тікет на той самий robot+параметр?"""
    q = (select(Ticket)
         .options(selectinload(Ticket.comments))
         .where(and_(Ticket.robot_id == robot_id,
                     Ticket.status.in_(OPEN_STATUSES)))
         .order_by(Ticket.created_at.desc()))
    for t in (await db.execute(q)).scalars():

        if t.anomaly_id:
            ev = await db.get(AnomalyEvent, t.anomaly_id)
            if ev and ev.parameter == parameter:
                return t

        expected = PARAM_TITLE.get(parameter, "")
        if expected and t.title.startswith(expected.split(":")[0]):
            return t
    return None


async def _pick_assignee(db: AsyncSession) -> Optional[UUID]:
    """Обрати виконавця авто-заявки: інженер з надійності, інакше адмін."""
    for role in ("engineer", "admin"):
        u = (await db.execute(
            select(User).where(User.role == role, User.is_active.is_(True))
            .order_by(User.created_at).limit(1)
        )).scalars().first()
        if u:
            return u.id
    return None


async def create_from_anomaly(
    db: AsyncSession,
    ev: AnomalyEvent,
    *,
    force: bool = False,
    created_by_user_id: Optional[UUID] = None,
) -> Optional[Ticket]:
    """Створити Ticket з AnomalyEvent.  Повертає None якщо severity не
    тригерить auto і ``force=False``.

    ``force=True`` — обхідний шлях для ручного "Створити заявку" з UI на
    warning-аномалію.
    """
    severity = (ev.severity or "warning").lower()
    if not force and severity not in ("critical", "emergency"):
        return None


    existing = await _open_ticket_for_param(db, ev.robot_id, ev.parameter)
    if existing:
        comment = TicketComment(
            ticket_id=existing.id, user_id=created_by_user_id,
            body=(f"⚠️ Повторна аномалія {severity}: "
                  f"{ev.parameter}={ev.value:.2f} (поріг {ev.threshold:.2f}). "
                  f"AnomalyEvent ID: {ev.id}."),
        )
        db.add(comment)

        priority_rank = {"low": 0, "medium": 1, "high": 2, "urgent": 3}
        new_pri = SEVERITY_MAP.get(severity, ("predictive", "medium"))[1]
        if priority_rank.get(new_pri, 1) > priority_rank.get(existing.priority, 1):
            existing.priority = new_pri
        await db.flush()
        log.info("auto_ticket: escalated existing ticket %s (robot=%s)",
                 existing.id, ev.robot_id)
        return existing

    component = await _find_component(db, ev.robot_id, ev.parameter)
    title = PARAM_TITLE.get(ev.parameter, f"Аномалія {ev.parameter}")
    robot = await db.get(Robot, ev.robot_id)
    title_full = f"{title} ({robot.code})" if robot else title


    assignee = await _pick_assignee(db)

    mtype, priority = SEVERITY_MAP.get(severity, ("predictive", "medium"))
    description = (
        f"Автоматично створена заявка з анімалії.\n\n"
        f"• Робот: {robot.code if robot else ev.robot_id}\n"
        f"• Параметр: {ev.parameter}\n"
        f"• Зафіксоване значення: {ev.value:.2f}\n"
        f"• Поріг: {ev.threshold:.2f}\n"
        f"• Severity: {severity}\n"
        f"• Час: {ev.detected_at.isoformat()}\n\n"
        f"{ev.message}"
    )

    ticket = Ticket(
        robot_id=ev.robot_id,
        component_id=component.id if component else None,
        anomaly_id=ev.id,
        title=title_full,
        description=description,
        maintenance_type=mtype,
        priority=priority,
        status="assigned" if assignee else "open",
        created_by=created_by_user_id,
        assigned_to=assignee,
    )
    db.add(ticket)
    await db.flush()

    q = select(Ticket).where(Ticket.id == ticket.id).options(selectinload(Ticket.comments))
    ticket = (await db.execute(q)).scalar_one()
    _emit("create", ticket)
    log.info("auto_ticket: created %s for anomaly %s (robot=%s, severity=%s)",
             ticket.id, ev.id, robot.code if robot else ev.robot_id, severity)
    return ticket
