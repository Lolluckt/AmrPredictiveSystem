"""Alert rule CRUD + anomaly events feed."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from ..core.deps import require_permission
from ..core.roles import Permission
from ..db import get_session
from ..models.alert import AlertRule, AnomalyEvent
from ..models.ticket import Ticket
from ..models.user import User
from ..schemas.alert import AlertRuleIn, AlertRuleOut, AnomalyOut
from ..schemas.ticket import TicketOut
from ..services.audit import record as audit
from ..services.auto_ticket import create_from_anomaly
from ..services.event_bus import bus

router = APIRouter(prefix="/api", tags=["alerts"])


def _emit_rule(action: str, rule: AlertRule) -> None:
    bus.publish("alert_rule", action, entity_id=rule.id,
                data=AlertRuleOut.model_validate(rule).model_dump(mode="json"))


def _emit_anomaly(action: str, ev: AnomalyEvent) -> None:
    bus.publish("anomaly", action, entity_id=ev.id, robot_id=ev.robot_id,
                data=AnomalyOut.model_validate(ev).model_dump(mode="json"))


@router.get("/alert-rules", response_model=list[AlertRuleOut])
async def list_rules(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.ALERTS_VIEW)),
) -> list[AlertRule]:
    res = await db.execute(select(AlertRule).order_by(AlertRule.name))
    return list(res.scalars())


@router.post("/alert-rules", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: AlertRuleIn,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.ALERTS_MANAGE)),
) -> AlertRule:
    rule = AlertRule(**payload.model_dump())
    db.add(rule)
    await audit(db, user_id=user.id, action="alert_rule.create",
                entity_type="alert_rule", entity_id=rule.id,
                details=payload.model_dump())
    await db.commit()
    await db.refresh(rule)
    _emit_rule("create", rule)
    return rule


@router.patch("/alert-rules/{rule_id}", response_model=AlertRuleOut)
async def update_rule(
    rule_id: UUID,
    payload: AlertRuleIn,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.ALERTS_MANAGE)),
) -> AlertRule:
    rule = await db.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    changes = payload.model_dump()
    for k, v in changes.items():
        setattr(rule, k, v)
    await audit(db, user_id=user.id, action="alert_rule.update",
                entity_type="alert_rule", entity_id=rule.id, details=changes)
    await db.commit()
    await db.refresh(rule)
    _emit_rule("update", rule)
    return rule


@router.delete("/alert-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.ALERTS_MANAGE)),
):
    rule = await db.get(AlertRule, rule_id)
    if rule:
        await audit(db, user_id=user.id, action="alert_rule.delete",
                    entity_type="alert_rule", entity_id=rule.id,
                    details={"name": rule.name})
        await db.delete(rule)
        await db.commit()
        bus.publish("alert_rule", "delete", entity_id=rule_id,
                    data={"id": str(rule_id)})


@router.get("/anomalies", response_model=list[AnomalyOut])
async def list_anomalies(
    robot_id: Optional[UUID] = None,
    unresolved: bool = Query(True, description="Лише не вирішені"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.ALERTS_VIEW)),
) -> list[AnomalyOut]:
    q = select(AnomalyEvent).order_by(AnomalyEvent.detected_at.desc()).limit(limit)
    if robot_id:
        q = q.where(AnomalyEvent.robot_id == robot_id)
    if unresolved:
        q = q.where(AnomalyEvent.resolved_at.is_(None))
    events = list((await db.execute(q)).scalars())


    ack_ids = {e.acknowledged_by for e in events if e.acknowledged_by}
    names: dict = {}
    if ack_ids:
        rows = (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(ack_ids)))).all()
        names = {r[0]: r[1] for r in rows}

    out: list[AnomalyOut] = []
    for e in events:
        ao = AnomalyOut.model_validate(e)
        ao.acknowledged_by_name = names.get(e.acknowledged_by)
        out.append(ao)
    return out


@router.post("/anomalies/{anomaly_id}/ack", response_model=AnomalyOut)
async def acknowledge(
    anomaly_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.ALERTS_ACK)),
) -> AnomalyEvent:
    ev = await db.get(AnomalyEvent, anomaly_id)
    if not ev:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if ev.acknowledged_at is None:
        ev.acknowledged_at = datetime.now(timezone.utc)
        ev.acknowledged_by = user.id
        await audit(db, user_id=user.id, action="anomaly.ack",
                    entity_type="anomaly", entity_id=ev.id)
        await db.commit()
        await db.refresh(ev)
        _emit_anomaly("ack", ev)
    return ev


@router.post("/anomalies/{anomaly_id}/ticket", response_model=TicketOut,
             status_code=status.HTTP_201_CREATED)
async def create_ticket_from_anomaly(
    anomaly_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.TICKETS_CREATE)),
):
    """Ручне створення CMMS-заявки з аномалії.

    Дозволено лише ПІСЛЯ підтвердження аномалії оператором/інженером — так
    фіксується, хто визнав подію перед заведенням наряду на ТО.  Для
    critical/emergency тікет уже створено автоматично; повторний виклик
    через dedup-логіку поверне наявний.
    """
    ev = await db.get(AnomalyEvent, anomaly_id)
    if not ev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Аномалію не знайдено")

    if ev.acknowledged_at is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Спершу підтвердьте аномалію — лише після цього можна створити заявку.",
        )
    ticket_id = None
    try:
        ticket = await create_from_anomaly(db, ev, force=True,
                                           created_by_user_id=user.id)
        if not ticket:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Не вдалося створити заявку з цієї аномалії")
        ticket_id = ticket.id
        await audit(db, user_id=user.id, action="ticket.create_from_anomaly",
                    entity_type="ticket", entity_id=ticket.id,
                    details={"anomaly_id": str(anomaly_id),
                             "robot_id": str(ev.robot_id),
                             "severity": ev.severity})
        await db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Помилка створення заявки: {exc}")


    q = (select(Ticket).where(Ticket.id == ticket_id)
         .options(selectinload(Ticket.comments)))
    return (await db.execute(q)).scalar_one()


@router.post("/anomalies/{anomaly_id}/resolve", response_model=AnomalyOut)
async def resolve(
    anomaly_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.ALERTS_ACK)),
) -> AnomalyEvent:
    ev = await db.get(AnomalyEvent, anomaly_id)
    if not ev:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    ev.resolved_at = datetime.now(timezone.utc)
    if ev.acknowledged_at is None:
        ev.acknowledged_at = ev.resolved_at
        ev.acknowledged_by = user.id
    await audit(db, user_id=user.id, action="anomaly.resolve",
                entity_type="anomaly", entity_id=ev.id)
    await db.commit()
    await db.refresh(ev)
    _emit_anomaly("resolve", ev)
    return ev
