"""Rule-based anomaly detection — evaluated on every ingested snapshot.

Підтримує два режими:
    * ``static``   — класичний пороговий: ``value op threshold``.
    * ``adaptive`` — поріг обчислюється з ковзного середнього і стандартного
      відхилення за останні ``window_minutes`` хвилин телеметрії саме цього
      робота саме за цим параметром.  Це дає одразу 3 переваги перед
      статичним порогом:
        1) автоматична нормалізація під дрейф сенсорів і температуру цеху;
        2) виявлення раптових (statistical outlier) аномалій, навіть якщо
           значення ще не перетнуло абсолютний поріг;
        3) скорочення false-negative при міжсерійному розкиді обладнання.

Кешуємо обчислений динамічний поріг на 30 секунд, щоб не робити SQL-агрегат
на кожен snapshot — це дозволяє системі тримати телеметрію 30+ роботів.

Кожне (robot_id, rule_id) має cooldown ``COOLDOWN`` хвилин, щоб одне
тривале перевищення не плодило сотні дублів.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.alert import AlertRule, AnomalyEvent
from ..models.telemetry import TelemetrySnapshot

OPS = {
    ">":  lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<":  lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


PARAM_ATTR = {
    "battery_soc":     "battery_soc",
    "battery_soh":     "battery_soh",
    "battery_temp":    "battery_temp",
    "battery_voltage": "battery_voltage",
    "left_motor_temp":  "left_motor_temp",
    "right_motor_temp": "right_motor_temp",
    "left_motor_vib":   "left_motor_vib",
    "right_motor_vib":  "right_motor_vib",
}


COOLDOWN = timedelta(minutes=2)


_state: Dict[Tuple[UUID, UUID], Dict[str, object]] = {}


_adaptive_cache: Dict[Tuple[UUID, str, int], Tuple[datetime, float, float]] = {}
ADAPTIVE_CACHE_TTL = timedelta(seconds=30)


async def _adaptive_stats(
    db: AsyncSession, robot_id: UUID, parameter: str, window_minutes: int
) -> Optional[Tuple[float, float]]:
    """Повертає (mean, std) параметра за останні ``window_minutes`` хвилин
    телеметрії робота.  Кешує на ``ADAPTIVE_CACHE_TTL``.

    Якщо точок менше 5 — повертає None (caller fallback'не на static).
    """
    key = (robot_id, parameter, window_minutes)
    now = datetime.now(timezone.utc)
    cached = _adaptive_cache.get(key)
    if cached and (now - cached[0]) < ADAPTIVE_CACHE_TTL:
        return cached[1], cached[2]

    col = getattr(TelemetrySnapshot, parameter, None)
    if col is None:
        return None
    cutoff = now - timedelta(minutes=window_minutes)
    q = (select(func.avg(col), func.stddev_samp(col), func.count(col))
         .where(TelemetrySnapshot.robot_id == robot_id,
                TelemetrySnapshot.recorded_at >= cutoff,
                col.is_not(None)))
    row = (await db.execute(q)).one()
    avg, std, n = row[0], row[1], row[2]
    if n is None or n < 5 or avg is None:
        return None
    std = float(std) if std is not None else 0.0
    avg = float(avg)
    _adaptive_cache[key] = (now, avg, std)
    return avg, std


def _effective_threshold(rule: AlertRule, stats: Optional[Tuple[float, float]]) -> float:
    """Для статичного режиму повертає ``rule.threshold``.
    Для адаптивного — ``mean ± k·σ`` залежно від оператора.
    """
    if rule.mode != "adaptive" or stats is None:
        return rule.threshold
    mean, std = stats
    if rule.operator in (">", ">="):
        return mean + rule.k_sigma * std
    if rule.operator in ("<", "<="):
        return mean - rule.k_sigma * std

    return rule.threshold


async def evaluate_snapshot(
    db: AsyncSession, robot_id: UUID, snap: TelemetrySnapshot
) -> list[AnomalyEvent]:
    """Check every enabled rule against one snapshot; persist any events."""
    rules = list((await db.execute(
        select(AlertRule).where(AlertRule.is_enabled.is_(True))
    )).scalars())
    events: list[AnomalyEvent] = []
    now = datetime.now(timezone.utc)

    for rule in rules:
        attr = PARAM_ATTR.get(rule.parameter)
        if not attr:
            continue
        value = getattr(snap, attr, None)
        if value is None:
            continue
        op = OPS.get(rule.operator)
        if not op:
            continue


        stats = None
        if rule.mode == "adaptive":
            stats = await _adaptive_stats(db, robot_id, attr, rule.window_minutes)
        threshold_eff = _effective_threshold(rule, stats)
        breached = op(value, threshold_eff)
        key = (robot_id, rule.id)
        st = _state.setdefault(key, {"last_fired": None, "tripped": False})

        if not breached:

            st["tripped"] = False
            continue

        last_fired = st.get("last_fired")
        if isinstance(last_fired, datetime) and (now - last_fired) < COOLDOWN:
            continue
        if st["tripped"] and isinstance(last_fired, datetime)\
                and (now - last_fired) < COOLDOWN:
            continue

        if rule.mode == "adaptive" and stats is not None:
            mean, std = stats
            msg = (f"{rule.name} [адапт]: {rule.parameter}={value:.2f} "
                   f"{rule.operator} {threshold_eff:.2f} "
                   f"(μ={mean:.2f}, σ={std:.2f}, k={rule.k_sigma}).")
        else:
            msg = (f"{rule.name}: {rule.parameter}={value:.2f} {rule.operator} "
                   f"{threshold_eff:.2f} (поріг).")
        ev = AnomalyEvent(
            robot_id=robot_id,
            rule_id=rule.id,
            severity=rule.severity,
            parameter=rule.parameter,
            value=float(value),
            threshold=float(threshold_eff),
            message=msg,
            detected_at=now,
        )
        db.add(ev)
        events.append(ev)
        st["last_fired"] = now
        st["tripped"] = True

    return events
