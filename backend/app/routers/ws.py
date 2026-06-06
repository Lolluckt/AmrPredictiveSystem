"""Real-time WebSocket channel.

Connect with::

    ws://<host>/api/ws?token=<JWT>

The token is the same access JWT used for HTTP requests; we accept it via
query string because browsers can't set custom headers on WebSocket
connections.

Message protocol (server → client only, single-direction):
    {"type":"hello",       "history":[...recent events...]}
    {"type":"telemetry",   "robot_id":..., "data":{...}}
    {"type":"robot",       "action":"update", "id":..., "data":{...}}
    {"type":"anomaly",     "action":"create", ...}
    {"type":"ticket",      "action":"create|patch|comment", ...}
    {"type":"mission",     "action":"create|patch|cancel", ...}
    {"type":"alert_rule",  "action":"create|patch|delete", ...}
    {"type":"ping"}                  ← server heartbeat (every 25s)

The client may send a "pong" string back; we ignore message content beyond
keeping the connection alive.
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from ..core.security import decode_token
from ..db import SessionLocal
from ..models.user import User
from ..services.event_bus import bus

log = logging.getLogger("ws")

router = APIRouter(prefix="/api", tags=["ws"])


async def _authenticate(token: str | None) -> User | None:
    if not token:
        return None
    claims = decode_token(token)
    if not claims or claims.get("typ") != "access":
        return None
    try:
        user_id = UUID(claims["sub"])
    except (KeyError, ValueError):
        return None
    async with SessionLocal() as db:
        user = await db.get(User, user_id)
        if not user or not user.is_active:
            return None
        return user


@router.websocket("/ws")
async def ws_channel(websocket: WebSocket, token: str | None = Query(default=None)):
    user = await _authenticate(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    queue = bus.subscribe()
    log.info("WS connected: %s (%s)", user.email, user.role)

    try:

        await websocket.send_json({
            "type": "hello",
            "user": {"id": str(user.id), "email": user.email, "role": user.role},
            "history": list(bus.recent(50)),
        })

        async def heartbeat():
            while True:
                await asyncio.sleep(25)
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    return

        async def reader():


            while True:
                try:
                    await websocket.receive_text()
                except WebSocketDisconnect:
                    return
                except Exception:
                    return

        hb_task = asyncio.create_task(heartbeat())
        rd_task = asyncio.create_task(reader())

        try:
            while True:
                ev = await queue.get()
                await websocket.send_json(ev)
        except WebSocketDisconnect:
            pass
        finally:
            hb_task.cancel()
            rd_task.cancel()
    except Exception as exc:
        log.warning("WS error for %s: %s", user.email, exc)
    finally:
        bus.unsubscribe(queue)
        try:
            await websocket.close()
        except Exception:
            pass
        log.info("WS disconnected: %s", user.email)
