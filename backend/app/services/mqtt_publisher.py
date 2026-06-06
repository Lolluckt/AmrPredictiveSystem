"""Thin wrapper for publishing commands back to robots.

The backend uses this when an operator clicks "Stop" or an engineer injects
a demo fault via the UI.  It is a no-op if MQTT is disabled, returns False
if the broker is unreachable, and is safe to call from request handlers
without blocking the event loop.

The topic is derived from the robot's mqtt_client_id by stripping the
``_client`` suffix that the seed adds — so ``amr_01_client`` becomes the
namespace ``factory/line_1/amr_01``, matching the controller's
subscription.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Optional

from ..config import get_settings

log = logging.getLogger("mqtt_publisher")

_client = None
_lock = threading.Lock()


def _client_or_none():
    """Lazily build (or return) the singleton paho client.  Thread-safe."""
    global _client
    settings = get_settings()
    if not settings.mqtt_enabled:
        return None
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return None

        try:
            c = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1,
                client_id="amr_pdm_backend_pub",
                clean_session=True,
                protocol=mqtt.MQTTv311,
            )
        except (AttributeError, TypeError):
            c = mqtt.Client(
                client_id="amr_pdm_backend_pub",
                clean_session=True,
                protocol=mqtt.MQTTv311,
            )
        c.reconnect_delay_set(min_delay=1, max_delay=30)
        try:
            c.connect(settings.mqtt_broker, settings.mqtt_port, keepalive=60)
            c.loop_start()
            _client = c
            log.info("MQTT publisher connected to %s:%s",
                     settings.mqtt_broker, settings.mqtt_port)
            return c
        except Exception as exc:
            log.exception("MQTT publisher connect failed: %s", exc)
            return None


def _topic_namespace(mqtt_client_id: str) -> str:
    """Translate ``amr_01_client`` (and a couple of common variants) into
    ``factory/line_1/amr_01`` so the message reaches the right controller.
    """
    base = mqtt_client_id.split("_client", 1)[0]
    base = base.split("_controller", 1)[0]
    if "/" in base:
        return base
    return f"factory/line_1/{base}"


def publish_command(mqtt_client_id: str, payload: dict[str, Any]) -> bool:
    c = _client_or_none()
    if c is None:
        log.warning("publish_command skipped — MQTT publisher unavailable")
        return False
    topic = f"{_topic_namespace(mqtt_client_id)}/commands"
    try:
        info = c.publish(topic, json.dumps(payload), qos=1)

        return getattr(info, "rc", 0) == 0
    except Exception as exc:
        log.exception("publish_command failed: %s", exc)
        return False


def publish_mission_assignment(
    mqtt_client_id: str, mission_id: str, *, action: str = "assigned",
    extra: Optional[dict] = None,
) -> bool:
    """Notify a controller that a logistics mission has been assigned/cancelled."""
    payload = {"command": "mission", "mission_id": mission_id, "action": action}
    if extra:
        payload.update(extra)
    return publish_command(mqtt_client_id, payload)
