"""Audit-log helper.

Every state-changing endpoint should call ``record(...)`` so that admins
have an immutable trail of who did what.  The function never raises — if
the audit insert fails it just logs the issue.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditLog
from ..services.event_bus import bus, _stringify

log = logging.getLogger("audit")


async def record(
    db: AsyncSession,
    *,
    user_id: Optional[UUID],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[Any] = None,
    details: Optional[dict] = None,
    publish: bool = True,
) -> None:
    """Persist an audit row and (by default) push it onto the event bus.

    Caller is responsible for committing the surrounding transaction.
    """
    try:
        row = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=_stringify(details) if details else None,
        )
        db.add(row)


        if publish:
            bus.publish(
                "audit", action,
                entity_id=entity_id,
                data={
                    "entity_type": entity_type,
                    "user_id": str(user_id) if user_id else None,
                    "details": details,
                },
            )
    except Exception as exc:
        log.warning("audit.record failed: %s", exc)
