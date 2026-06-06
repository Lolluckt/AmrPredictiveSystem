"""Background MQTT ingestor.

Subscribes to the wildcard telemetry pattern, parses each JSON message,
writes a TelemetrySnapshot, evaluates alert rules, updates the robot
live-state (status / last_x / last_y / last_seen_at) and pushes a live
event onto the in-process bus so connected WebSocket clients update
without polling.

Paho-MQTT is a sync client: the network loop runs on its own thread and
the on_message callback hops into the asyncio loop via
``run_coroutine_threadsafe``.  The async consumer batches by
(robot_code, ts) for up to ``FLUSH_INTERVAL`` so the six telemetry
sections published per tick land in one DB row.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from ..config import get_settings
from ..db import session_scope
from ..models.robot import Robot
from ..models.telemetry import TelemetrySnapshot
from .anomaly import evaluate_snapshot
from .auto_ticket import create_from_anomaly
from .event_bus import bus

log = logging.getLogger("mqtt_ingest")

FLUSH_INTERVAL = 1.5
MAX_BUFFER     = 32


class MqttIngestor:
    def __init__(self, queue: asyncio.Queue) -> None:
        self.settings = get_settings()
        self.queue = queue
        self._client = None
        self._thread_loop: Optional[asyncio.AbstractEventLoop] = None


    def _on_connect(self, client, userdata, flags, rc, properties=None):
        log.info("MQTT ingest connected rc=%s; subscribing %s",
                 rc, self.settings.mqtt_topic_pattern)
        client.subscribe(self.settings.mqtt_topic_pattern, qos=0)

    def _on_disconnect(self, client, userdata, rc, properties=None):
        log.warning("MQTT ingest disconnected rc=%s — paho will auto-reconnect", rc)

    def _on_message(self, client, userdata, msg):

        parts = msg.topic.split("/")
        if len(parts) < 5 or parts[3] != "telemetry":
            return
        robot_code = parts[2]
        section = parts[4]
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            log.warning("Bad JSON on %s", msg.topic)
            return
        if self._thread_loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.queue.put({"robot_code": robot_code, "section": section, "data": payload}),
                self._thread_loop,
            )
        except Exception as exc:
            log.warning("ingest enqueue failed: %s", exc)


    async def start(self) -> None:
        if not self.settings.mqtt_enabled:
            log.info("MQTT ingest disabled (MQTT_ENABLED=false)")
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            log.error("paho-mqtt not installed; ingest disabled")
            return
        self._thread_loop = asyncio.get_running_loop()


        try:
            c = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1,
                client_id="amr_pdm_backend_ingest",
                clean_session=True,
                protocol=mqtt.MQTTv311,
            )
        except (AttributeError, TypeError):
            c = mqtt.Client(
                client_id="amr_pdm_backend_ingest",
                clean_session=True,
                protocol=mqtt.MQTTv311,
            )
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        c.on_message = self._on_message
        c.reconnect_delay_set(min_delay=1, max_delay=30)
        try:
            c.connect_async(self.settings.mqtt_broker, self.settings.mqtt_port, keepalive=60)
            c.loop_start()
            self._client = c
            log.info("MQTT ingest started (%s:%s)",
                     self.settings.mqtt_broker, self.settings.mqtt_port)
        except Exception as exc:
            log.exception("MQTT connect failed: %s", exc)

    async def stop(self) -> None:
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass


async def consume_queue(queue: asyncio.Queue) -> None:
    """Assemble messages (one per section) into a snapshot keyed by
    robot+ts and persist + evaluate alerts.

    The controller publishes six small sections per TELEMETRY_INTERVAL.
    We buffer by (robot_code, ts) for FLUSH_INTERVAL seconds before
    flushing — that way one DB row holds the whole batch.
    """
    buffer: dict[tuple[str, float], dict] = {}
    last_flush = asyncio.get_running_loop().time()

    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=0.5)
            key = (item["robot_code"], item["data"].get("ts", 0))
            buffer.setdefault(key, {})[item["section"]] = item["data"]
        except asyncio.TimeoutError:
            pass

        now = asyncio.get_running_loop().time()
        should_flush = (now - last_flush >= FLUSH_INTERVAL) or len(buffer) >= MAX_BUFFER
        if not should_flush or not buffer:
            continue

        last_flush = now
        to_flush, buffer = buffer, {}

        try:
            async with session_scope() as db:
                for (robot_code, _ts), payload in to_flush.items():
                    await _persist(db, robot_code, payload)
        except Exception:
            log.exception("ingest flush failed")


async def _persist(db, robot_code: str, payload: dict) -> None:
    """Turn one assembled telemetry batch into a snapshot + anomaly events."""


    q = await db.execute(
        select(Robot).where(
            (Robot.mqtt_client_id.like(f"{robot_code}%"))
            | (Robot.code == robot_code.replace("amr_", "AMR-").upper())
            | (Robot.code.ilike(robot_code))
        )
    )
    robot = q.scalars().first()
    if not robot:
        return

    pos   = payload.get("position", {})  or {}
    batt  = payload.get("battery", {})   or {}
    motor = payload.get("motors", {})    or {}
    mission = payload.get("mission", {}) or {}
    left  = motor.get("left", {})  if isinstance(motor.get("left"),  dict) else {}
    right = motor.get("right", {}) if isinstance(motor.get("right"), dict) else {}

    now = datetime.now(timezone.utc)
    snap = TelemetrySnapshot(
        robot_id=robot.id,
        recorded_at=now,
        pos_x=pos.get("x"), pos_y=pos.get("y"),
        heading_deg=pos.get("heading"), zone=pos.get("zone"),
        battery_soc=batt.get("soc"), battery_soh=batt.get("soh"),
        battery_voltage=batt.get("voltage"), battery_current=batt.get("current"),
        battery_temp=batt.get("temperature"), battery_internal_r=batt.get("internal_resistance"),
        left_motor_temp=left.get("temperature"), right_motor_temp=right.get("temperature"),
        left_motor_vib=left.get("vibration"),    right_motor_vib=right.get("vibration"),
        left_motor_eff=left.get("efficiency"),   right_motor_eff=right.get("efficiency"),
        odometry_m=mission.get("odometry_m"),    state=mission.get("state"),
        mission_step=mission.get("step"),
        raw=payload,
    )
    db.add(snap)


    prev_status = robot.status
    was_charging = (prev_status == "charging")
    if pos.get("x") is not None:
        robot.last_x = pos["x"]; robot.last_y = pos["y"]
        robot.last_heading_deg = pos.get("heading")
        robot.last_zone = pos.get("zone")
    robot.last_seen_at = now
    if batt.get("is_charging"):
        robot.status = "charging"
    elif (mission.get("state") or "") == "idle":
        robot.status = "idle"
    else:
        robot.status = "operational"


    if was_charging and robot.status != "charging":
        from .dock_allocator import release as _release_dock
        try:
            await _release_dock(db, robot.id)
        except Exception:
            log.exception("dock release failed for robot %s", robot.code)


    if mission.get("odometry_m") is not None:
        robot.total_odometry_m = max(robot.total_odometry_m or 0.0,
                                     float(mission["odometry_m"]))


    if mission.get("cycle") is not None:
        robot.total_missions = max(robot.total_missions or 0,
                                   int(mission["cycle"]))

    await db.flush()


    bus.publish(
        "telemetry", "update", robot_id=robot.id,
        data={
            "robot_id":  str(robot.id),
            "robot_code": robot.code,
            "ts":         now.isoformat(),
            "pos_x":      snap.pos_x,
            "pos_y":      snap.pos_y,
            "heading":    snap.heading_deg,
            "zone":       snap.zone,
            "status":     robot.status,
            "battery_soc":  snap.battery_soc,
            "battery_temp": snap.battery_temp,
            "left_motor_temp":  snap.left_motor_temp,
            "right_motor_temp": snap.right_motor_temp,
            "left_motor_vib":   snap.left_motor_vib,
            "right_motor_vib":  snap.right_motor_vib,
            "state":      snap.state,
            "odometry_m": snap.odometry_m,
        },
    )

    if robot.status != prev_status:
        bus.publish(
            "robot", "status",
            robot_id=robot.id,
            entity_id=robot.id,
            data={"id": str(robot.id), "code": robot.code,
                  "status": robot.status, "previous": prev_status},
        )

    events = await evaluate_snapshot(db, robot.id, snap)
    if events:
        await db.flush()


        sev_rank = {"info": 0, "warning": 1, "critical": 2, "emergency": 3}
        top_sev = max((e.severity for e in events),
                      key=lambda s: sev_rank.get(s, 0), default=None)
        if top_sev in ("critical", "emergency") and robot.status != "charging":
            robot.status = "critical"
            await db.flush()

        for ev in events:
            bus.publish(
                "anomaly", "create",
                robot_id=robot.id,
                entity_id=ev.id,
                data={
                    "id":         str(ev.id),
                    "robot_id":   str(ev.robot_id),
                    "rule_id":    str(ev.rule_id) if ev.rule_id else None,
                    "severity":   ev.severity,
                    "parameter":  ev.parameter,
                    "value":      ev.value,
                    "threshold":  ev.threshold,
                    "message":    ev.message,
                    "detected_at": ev.detected_at.isoformat(),
                },
            )


            try:
                await create_from_anomaly(db, ev)
            except Exception:
                log.exception("auto_ticket failed for event %s", ev.id)
