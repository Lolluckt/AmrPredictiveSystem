"""Lightweight in-process pub/sub used to broadcast domain events to
WebSocket subscribers.

The bus keeps a small ring-buffer of recent events so that a freshly-
connected client can backfill what happened in the last few seconds, and
fans out new events to every active subscriber via per-subscriber
``asyncio.Queue``.

Event envelope::

    {
        "type":   "telemetry|robot|anomaly|ticket|mission|alert_rule|user|audit",
        "action": "update|create|patch|delete|ack|resolve|...",
        "id":     "<uuid|None>",
        "robot_id": "<uuid|None>",
        "data":   {...},        # payload (typically the row as a dict)
        "ts":     "<ISO-8601>",
    }

Designed to run inside a single-process FastAPI app.  For multi-replica
deployments swap the storage with Redis pub/sub (the public API stays the
same).
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Iterable, Optional, Set
from uuid import UUID

log = logging.getLogger("event_bus")


def _stringify(obj: Any) -> Any:
    """JSON-friendly conversion for UUIDs/datetimes/Decimal/etc."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _stringify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_stringify(v) for v in obj]
    if hasattr(obj, "__dict__") and not isinstance(obj, (str, bytes)):

        try:
            return {k: _stringify(v) for k, v in vars(obj).items()
                    if not k.startswith("_")}
        except Exception:
            return repr(obj)
    return obj


class EventBus:
    """Singleton-style fan-out queue.

    Subscribers call ``subscribe()`` to receive a queue, and emit code calls
    ``publish()`` from any task to push an event.  If a subscriber is too
    slow we silently drop messages for that subscriber rather than
    back-pressure the producers.
    """

    def __init__(self, history: int = 200, sub_queue_size: int = 500) -> None:
        self._subscribers: Set[asyncio.Queue] = set()
        self._history: Deque[Dict[str, Any]] = deque(maxlen=history)
        self._sub_queue_size = sub_queue_size
        self._lock = asyncio.Lock()


    def publish(
        self,
        event_type: str,
        action: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        robot_id: Optional[Any] = None,
        entity_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        envelope: Dict[str, Any] = {
            "type": event_type,
            "action": action,
            "id": str(entity_id) if entity_id is not None else None,
            "robot_id": str(robot_id) if robot_id is not None else None,
            "data": _stringify(data) if data is not None else None,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(envelope)

        for q in tuple(self._subscribers):
            try:
                q.put_nowait(envelope)
            except asyncio.QueueFull:

                try:
                    q.get_nowait()
                    q.put_nowait(envelope)
                except Exception:
                    log.warning("event_bus: dropping event for slow subscriber")
        return envelope


    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._sub_queue_size)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def recent(self, limit: int = 50) -> Iterable[Dict[str, Any]]:
        items = list(self._history)
        return items[-limit:]


bus = EventBus()
