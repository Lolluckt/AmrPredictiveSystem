"""CMMS tickets — full kanban backend.

The frontend kanban supports the seven canonical statuses defined here.
Every state-changing call writes an audit row and broadcasts a live
event so the kanban updates without polling.
"""
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
from ..models.ticket import Ticket, TicketComment
from ..models.user import User
from ..schemas.ticket import (
    TicketCommentIn, TicketCommentOut,
    TicketCreate, TicketOut, TicketUpdate,
)
from ..services.audit import record as audit
from ..services.event_bus import bus

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

VALID_STATUSES = {
    "open", "assigned", "in_progress", "waiting_parts",
    "completed", "verified", "cancelled",
}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
VALID_TYPES = {"predictive", "preventive", "corrective", "emergency"}


def _emit(action: str, ticket: Ticket) -> None:
    bus.publish("ticket", action, entity_id=ticket.id, robot_id=ticket.robot_id,
                data=TicketOut.model_validate(ticket).model_dump(mode="json"))


def _validate(payload: TicketCreate | TicketUpdate) -> None:
    if getattr(payload, "priority", None) and payload.priority not in VALID_PRIORITIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "priority повинен бути одним із: " + ", ".join(VALID_PRIORITIES))
    if getattr(payload, "status", None) and payload.status not in VALID_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "status повинен бути одним із: " + ", ".join(VALID_STATUSES))
    if getattr(payload, "maintenance_type", None) and payload.maintenance_type not in VALID_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "maintenance_type повинен бути одним із: " + ", ".join(VALID_TYPES))


@router.get("", response_model=list[TicketOut])
async def list_tickets(
    status_filter: Optional[str] = Query(None, alias="status"),
    robot_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.TICKETS_VIEW)),
) -> list[Ticket]:
    q = select(Ticket).options(selectinload(Ticket.comments)).order_by(Ticket.created_at.desc())
    if status_filter:
        q = q.where(Ticket.status == status_filter)
    if robot_id:
        q = q.where(Ticket.robot_id == robot_id)
    return list((await db.execute(q)).scalars())


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.TICKETS_CREATE)),
) -> Ticket:
    _validate(payload)
    data = payload.model_dump()
    ticket = Ticket(**data, created_by=user.id, status="open")
    if payload.assigned_to:
        ticket.status = "assigned"
    db.add(ticket)
    await audit(db, user_id=user.id, action="ticket.create",
                entity_type="ticket", entity_id=ticket.id,
                details={"title": ticket.title, "robot_id": str(payload.robot_id)})
    await db.commit()

    q = select(Ticket).where(Ticket.id == ticket.id).options(selectinload(Ticket.comments))
    ticket = (await db.execute(q)).scalar_one()
    _emit("create", ticket)
    return ticket


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.TICKETS_VIEW)),
) -> Ticket:
    q = select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.comments))
    t = (await db.execute(q)).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return t


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: UUID,
    payload: TicketUpdate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.TICKETS_EDIT)),
) -> Ticket:
    _validate(payload)
    q = select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.comments))
    t = (await db.execute(q)).scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    changes = payload.model_dump(exclude_none=True)
    prev_status = t.status
    for k, v in changes.items():
        setattr(t, k, v)
    if payload.status in ("completed", "verified") and not t.completed_at:
        t.completed_at = datetime.now(timezone.utc)
    await audit(db, user_id=user.id, action="ticket.update",
                entity_type="ticket", entity_id=t.id,
                details={"changes": changes, "prev_status": prev_status})
    await db.commit()
    await db.refresh(t)
    _emit("update", t)
    return t


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.TICKETS_CLOSE)),
):
    t = await db.get(Ticket, ticket_id)
    if not t:
        return
    await audit(db, user_id=user.id, action="ticket.delete",
                entity_type="ticket", entity_id=t.id,
                details={"title": t.title})
    await db.delete(t)
    await db.commit()
    bus.publish("ticket", "delete", entity_id=ticket_id,
                data={"id": str(ticket_id)})


@router.post("/{ticket_id}/comments", response_model=TicketCommentOut, status_code=status.HTTP_201_CREATED)
async def add_comment(
    ticket_id: UUID,
    payload: TicketCommentIn,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission(Permission.TICKETS_VIEW)),
) -> TicketComment:
    t = await db.get(Ticket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    c = TicketComment(ticket_id=ticket_id, user_id=user.id, body=payload.body)
    db.add(c)
    await audit(db, user_id=user.id, action="ticket.comment",
                entity_type="ticket", entity_id=ticket_id,
                details={"comment_id": str(c.id), "body": payload.body[:200]})
    await db.commit()
    await db.refresh(c)
    bus.publish("ticket", "comment", entity_id=ticket_id, robot_id=t.robot_id,
                data={"ticket_id": str(ticket_id), "comment": {
                    "id": str(c.id), "body": c.body,
                    "user_id": str(c.user_id) if c.user_id else None,
                    "created_at": c.created_at.isoformat(),
                }})
    return c
