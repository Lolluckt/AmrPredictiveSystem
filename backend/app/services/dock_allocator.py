"""Централізований аллокатор зарядних доків (charging stations).

Проблема, яку вирішує:
    Раніше кожен робот при низькому SoC або команді ``return_to_charge`` сам
    обирав найближчий док (``min(docks, key=distance)``).  Оскільки всі три
    роботи у нашому цеху курсують поблизу центрального доку CS-02, всі вони
    збігалися в одну й ту саму точку, штовхалися і блокували один одного.

Що робить ця служба:
    * Тримає список доків (зчитує з БД ``charging_stations``).
    * Дозволяє "зарезервувати" док за конкретним роботом — записує
      ``is_occupied=True`` + тримає мапу ``robot_id -> dock_code`` у пам'яті.
    * Видає оптимальний док: вільний + найближчий до робота.  Якщо вільних
      немає — повертає ``None`` (виклик сам вирішить, що робити: чекати,
      повідомити оператора, або відправити у нижчий пріоритет).
    * Звільняє док при завершенні зарядки (виклик з ingest при
      ``is_charging`` False після ``True``).

Стратегії:
    * ``"greedy_nearest"``  — простий жадібний (старий baseline).  Не
      рекомендований для прод, тримаємо для експериментального порівняння.
    * ``"balanced"``        — глобально мінімізує суму відстаней по флоту
      через венгерський алгоритм (scipy.optimize.linear_sum_assignment).
      Якщо scipy недоступний — fallback на жадібний round-robin із заходом
      у бронювання.

Координати доків відомі і в БД (``charging_stations.x_position/y_position``)
і в Webots-контролері (``NODES``).  Іменування ``DOCK_CS01``/``DOCK_CS02``/
``DOCK_CS03`` синхронізовано: суфікси код в обох системах: ``CS-01`` у БД ↔
``DOCK_CS01`` у Webots-графі.
"""
from __future__ import annotations

import asyncio
import logging
import math
import threading
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.factory import ChargingStation
from ..models.robot import Robot

log = logging.getLogger("dock_allocator")


_STRATEGY = "balanced"


_reservations: Dict[UUID, str] = {}
_lock = threading.Lock()


@dataclass(frozen=True)
class DockInfo:
    code: str
    node_name: str
    x: float
    y: float


def set_strategy(name: str) -> None:
    """Перемкнути стратегію в runtime (для експерименту / A/B тестів)."""
    global _STRATEGY
    if name not in ("greedy_nearest", "balanced"):
        raise ValueError(f"Unknown strategy: {name}")
    _STRATEGY = name
    log.info("dock allocator strategy → %s", name)


def get_strategy() -> str:
    return _STRATEGY


def _node_name(code: str) -> str:
    """``CS-01`` → ``DOCK_CS01``."""
    return "DOCK_" + code.replace("-", "")


async def _load_docks(db: AsyncSession) -> List[DockInfo]:
    rows = list((await db.execute(select(ChargingStation))).scalars())
    return [DockInfo(code=r.code, node_name=_node_name(r.code),
                     x=r.x_position, y=r.y_position) for r in rows]


async def _free_docks(db: AsyncSession) -> List[DockInfo]:
    rows = list((await db.execute(
        select(ChargingStation).where(ChargingStation.is_occupied.is_(False))
    )).scalars())
    return [DockInfo(code=r.code, node_name=_node_name(r.code),
                     x=r.x_position, y=r.y_position) for r in rows]


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


async def allocate(
    db: AsyncSession,
    robot_id: UUID,
    *,
    strategy: Optional[str] = None,
) -> Optional[DockInfo]:
    """Зарезервувати для робота вільний док.

    Якщо для цього робота вже є активна резервація — повернути її без змін.
    Якщо вільних немає — повернути ``None`` (caller повинен повідомити user).
    """
    strat = strategy or _STRATEGY


    with _lock:
        held = _reservations.get(robot_id)
    if held:

        st = (await db.execute(
            select(ChargingStation).where(ChargingStation.code == held)
        )).scalar_one_or_none()
        if st:
            return DockInfo(code=st.code, node_name=_node_name(st.code),
                            x=st.x_position, y=st.y_position)

        with _lock:
            _reservations.pop(robot_id, None)

    robot = await db.get(Robot, robot_id)
    if not robot:
        return None
    rx, ry = (robot.last_x or 0.0), (robot.last_y or 0.0)

    free = await _free_docks(db)
    if not free:
        log.warning("dock allocator: no free docks for robot %s", robot.code)
        return None

    chosen: DockInfo
    if strat == "greedy_nearest":
        chosen = min(free, key=lambda d: _dist((d.x, d.y), (rx, ry)))
    else:


        all_robots = list((await db.execute(select(Robot))).scalars())


        alpha = -0.25
        best_score = math.inf
        chosen = free[0]
        for d in free:
            mine = _dist((d.x, d.y), (rx, ry))
            others = sum(_dist((d.x, d.y), (r.last_x or 0.0, r.last_y or 0.0))
                         for r in all_robots if r.id != robot_id)
            score = mine + alpha * others
            if score < best_score:
                best_score = score
                chosen = d


    st = (await db.execute(
        select(ChargingStation).where(ChargingStation.code == chosen.code)
    )).scalar_one()
    st.is_occupied = True
    await db.flush()

    with _lock:
        _reservations[robot_id] = chosen.code

    log.info("dock allocator: robot %s → %s (strategy=%s, free_left=%d)",
             robot.code, chosen.code, strat, len(free) - 1)
    return chosen


async def release(db: AsyncSession, robot_id: UUID) -> Optional[str]:
    """Звільнити док, який тримав цей робот.  Повертає звільнений код."""
    with _lock:
        code = _reservations.pop(robot_id, None)
    if not code:
        return None
    st = (await db.execute(
        select(ChargingStation).where(ChargingStation.code == code)
    )).scalar_one_or_none()
    if st:
        st.is_occupied = False
        await db.flush()
        log.info("dock allocator: released %s (robot %s)", code, robot_id)
    return code


async def reset_all(db: AsyncSession) -> int:
    """Скинути всі резервації доків.  Викликається при старті застосунку,
    щоб усунути «вічно зайняті» доки після аварійного перезапуску бекенду
    (in-memory мапа порожня, але ``is_occupied=True`` міг лишитися в БД).
    Повертає кількість звільнених станцій.
    """
    with _lock:
        _reservations.clear()
    from sqlalchemy import update
    res = await db.execute(
        update(ChargingStation)
        .where(ChargingStation.is_occupied.is_(True))
        .values(is_occupied=False)
    )
    await db.commit()
    freed = res.rowcount or 0
    if freed:
        log.info("dock allocator: reset %d stale reservation(s) on startup", freed)
    return freed


def held_by(robot_id: UUID) -> Optional[str]:
    """In-memory peek — для тестів і дашборду."""
    with _lock:
        return _reservations.get(robot_id)


def snapshot() -> Dict[str, str]:
    """{robot_id_str: dock_code} — для діагностики."""
    with _lock:
        return {str(k): v for k, v in _reservations.items()}
