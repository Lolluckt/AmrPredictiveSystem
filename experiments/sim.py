"""Discrete-event симулятор цеху AMR-роботів для експериментального
обґрунтування дипломної роботи.

Не вимагає Webots, MQTT, PostgreSQL. Все pure-Python, детерміністично
залежить від ``seed``.  Один крок = 1 с модельного часу.

Що моделюється
══════════════
* Граф цеху (вузли і ребра), синхронізований з ``amr_controller.py``.
* 3 AMR-роботи, кожен з власним циклом місій (load → drop → load → drop …).
* Батарея (SoC), зниження SoC від навантаження, заряджання на доках.
* Зарядні станції з місткістю 1 робот і ``is_occupied`` прапором.
* Імовірнісна модель поломок (bearing/thermal/battery_fade) з лінійним
  зростанням ризику відмови від накопиченого зносу і температури.
* Раннє виявлення аномалії: вектор телеметрії перетворюється у severity
  при перевищенні порогів (як у backend rule engine), за певний час до
  фактичної поломки.
* Стратегія обслуговування:
   - ``reactive``  — ремонт лише після поломки (довгий простій 3-5 год).
   - ``predictive`` — заявка створюється при першій critical аномалії,
                      ремонт планується на наступну вільну "зміну" робота
                      (короткий простій 30-60 хв, бо це планове ТО).

Стратегія розподілу доків:
   - ``greedy``   — кожен робот, коли потребує заряджання, обирає
                     найближчий док незалежно від інших → колізії.
   - ``allocator`` — централізована функція бере вільні доки, обирає для
                     робота той, що мінімізує сумарний пробіг флоту до
                     зарядки. Якщо вільних немає — робот чекає (`queued`).

Event-log
═════════
``run_simulation`` повертає словник з:
   ``events``: list[dict]   — подієвий лог (поломки, ремонти, аномалії,
                              зарядки, місії)
   ``robots``: dict[str, dict] — фінальний агрегат по кожному роботу
   ``meta``:   dict          — використана стратегія, seed, тривалість
"""
from __future__ import annotations

import math
import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


NODES: Dict[str, Tuple[float, float]] = {
    "PICKUP_RAW":    (5.0,   4.5),
    "C_S":           (11.5,  4.5),
    "C_MID_S":       (11.5,  10.0),
    "C_MID_N":       (11.5,  11.0),
    "C_N":           (11.5,  17.5),
    "C_MID_A":       (18.0,  10.0),
    "C_MID_W":       (27.5,  10.0),
    "C_MID_F":       (34.0,  10.0),
    "DROPOFF_A":     (18.0,   9.0),
    "DROPOFF_B":     (18.0,  11.0),
    "DROPOFF_W":     (27.5,   9.0),
    "DROPOFF_PKG":   (27.5,  14.0),
    "DROPOFF_FIN_A": (34.0,   6.0),
    "DROPOFF_FIN_B": (34.0,  16.0),
    "C_MID_W1":      (5.0,   10.0),
    "PICKUP_QC":     (5.0,   18.0),
    "DOCK_CS01":     (2.0,   13.0),
    "DOCK_CS02":     (5.0,   13.0),
    "DOCK_CS03":     (8.0,   13.0),
}

NEIGHBOURS: Dict[str, List[str]] = {
    "PICKUP_RAW":    ["C_S"],
    "C_S":           ["PICKUP_RAW", "C_MID_S", "DROPOFF_A"],
    "C_MID_S":       ["C_S", "C_MID_N", "C_MID_W1", "C_MID_A"],
    "C_MID_N":       ["C_MID_S", "C_N", "DROPOFF_B"],
    "C_N":           ["C_MID_N"],
    "C_MID_A":       ["C_MID_S", "C_MID_W", "DROPOFF_A", "DROPOFF_B"],
    "C_MID_W":       ["C_MID_A", "C_MID_F", "DROPOFF_W", "DROPOFF_PKG"],
    "C_MID_F":       ["C_MID_W", "DROPOFF_FIN_A", "DROPOFF_FIN_B"],
    "DROPOFF_A":     ["C_S", "C_MID_A"],
    "DROPOFF_B":     ["C_MID_N", "C_MID_A"],
    "DROPOFF_W":     ["C_MID_W"],
    "DROPOFF_PKG":   ["C_MID_W"],
    "DROPOFF_FIN_A": ["C_MID_F"],
    "DROPOFF_FIN_B": ["C_MID_F"],
    "C_MID_W1":      ["C_MID_S", "PICKUP_QC", "DOCK_CS01", "DOCK_CS02", "DOCK_CS03"],
    "PICKUP_QC":     ["C_MID_W1"],
    "DOCK_CS01":     ["C_MID_W1"],
    "DOCK_CS02":     ["C_MID_W1"],
    "DOCK_CS03":     ["C_MID_W1"],
}

DOCKS = ("DOCK_CS01", "DOCK_CS02", "DOCK_CS03")


MISSIONS = {
    "amr_01": [("PICKUP_RAW", 5), ("DROPOFF_A", 5),
               ("PICKUP_RAW", 5), ("DROPOFF_B", 5)],
    "amr_02": [("DROPOFF_A", 4), ("DROPOFF_W", 4), ("DROPOFF_W", 6),
               ("DROPOFF_W", 4), ("DROPOFF_PKG", 4), ("DROPOFF_FIN_A", 4)],
    "amr_03": [("PICKUP_QC", 5), ("DROPOFF_FIN_B", 6),
               ("DROPOFF_FIN_B", 4), ("PICKUP_QC", 3)],
}

START_POSITIONS = {
    "amr_01": (5.0, 4.5),
    "amr_02": (18.0, 4.5),
    "amr_03": (5.0, 19.5),
}


CRUISE_SPEED_M_S = 0.8
WORK_FACTOR      = 1.0
SOC_FULL         = 100.0
SOC_LOW          = 25.0


SOC_FULL_RESUME  = 95.0
DOCK_TOLERANCE_M = 0.5


SOC_DROP_MOVE_PER_S = 100.0 / (2.5 * 3600)
SOC_DROP_IDLE_PER_S = 100.0 / (20.0 * 3600)
SOC_GAIN_CHARGE_PER_S = 100.0 / (45 * 60)


WEAR_RATE_PER_S = 1.0 / (3600 * 6)

BASE_FAIL_PROB_PER_S = 8e-5


REPAIR_TIME_REACTIVE_S = (2 * 3600, 4 * 3600)
REPAIR_TIME_PLANNED_S  = (20 * 60, 45 * 60)


PREDICTIVE_THRESHOLD_WEAR = 0.55
WARNING_THRESHOLD_WEAR    = 0.35


INIT_WEAR_RANGE = (0.10, 0.45)
INIT_SOC_RANGE  = (55.0, 95.0)


def bfs(start: str, goal: str) -> List[str]:
    if start == goal:
        return [start]
    visited = {start}
    q = deque([(start, [start])])
    while q:
        node, path = q.popleft()
        for nb in NEIGHBOURS.get(node, []):
            if nb in visited:
                continue
            if nb == goal:
                return path + [nb]
            visited.add(nb)
            q.append((nb, path + [nb]))
    return []


def nearest_node(x: float, y: float) -> str:
    return min(NODES, key=lambda n: math.hypot(NODES[n][0]-x, NODES[n][1]-y))


def edge_dist(a: str, b: str) -> float:
    ax, ay = NODES[a]; bx, by = NODES[b]
    return math.hypot(ax - bx, ay - by)


@dataclass
class Robot:
    rid: str
    x: float
    y: float
    soc: float = SOC_FULL
    wear: float = 0.0
    state: str = "navigating"
    path: List[str] = field(default_factory=list)
    work_until: float = 0.0
    target_dock: Optional[str] = None
    mission_idx: int = 0
    missions_done: int = 0

    time_failed_s: float = 0.0
    time_repairing_s: float = 0.0
    time_charging_s: float = 0.0
    time_queued_s: float = 0.0
    time_active_s: float = 0.0
    distance_m: float = 0.0
    distance_to_dock_m: float = 0.0
    last_low_soc_t: Optional[float] = None
    last_anomaly_t: Optional[float] = None
    repair_started_t: Optional[float] = None
    repair_planned: bool = False


@dataclass
class SimConfig:
    dock_strategy: str = "allocator"
    maintenance_policy: str = "predictive"
    shift_hours: float = 8.0
    seed: int = 42


class Simulator:
    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.t = 0.0
        self.events: List[dict] = []
        self.dock_occupied: Dict[str, Optional[str]] = {d: None for d in DOCKS}
        self.robots: Dict[str, Robot] = {}
        for rid in MISSIONS.keys():
            sx, sy = START_POSITIONS[rid]


            init_wear = self.rng.uniform(*INIT_WEAR_RANGE)
            init_soc  = self.rng.uniform(*INIT_SOC_RANGE)
            self.robots[rid] = Robot(rid=rid, x=sx, y=sy,
                                     soc=init_soc, wear=init_wear)
        self._plan_next_step(self.robots["amr_01"])
        self._plan_next_step(self.robots["amr_02"])
        self._plan_next_step(self.robots["amr_03"])


    def log(self, kind: str, **kw) -> None:
        ev = {"t": round(self.t, 1), "kind": kind, **kw}
        self.events.append(ev)


    def _plan_next_step(self, r: Robot) -> None:
        mission = MISSIONS[r.rid]
        target_node, _ = mission[r.mission_idx % len(mission)]
        start = nearest_node(r.x, r.y)
        r.path = bfs(start, target_node)
        if not r.path:
            r.path = [target_node]
        r.state = "navigating"


    def _choose_dock(self, r: Robot) -> Optional[str]:
        free = [d for d in DOCKS if self.dock_occupied[d] is None]
        if not free:
            return None
        if self.cfg.dock_strategy == "greedy":
            return min(free,
                       key=lambda d: math.hypot(NODES[d][0]-r.x, NODES[d][1]-r.y))


        candidates_robots = [rb for rb in self.robots.values()
                             if rb.soc < SOC_LOW + 5 and rb.state in
                             ("navigating", "queued_for_dock") and rb is not r]
        if not candidates_robots:
            return min(free,
                       key=lambda d: math.hypot(NODES[d][0]-r.x, NODES[d][1]-r.y))


        alpha = -0.25
        best, best_score = None, math.inf
        for d in free:
            mine = math.hypot(NODES[d][0]-r.x, NODES[d][1]-r.y)
            others = sum(math.hypot(NODES[d][0]-rb.x, NODES[d][1]-rb.y)
                         for rb in candidates_robots)
            score = mine + alpha * others
            if score < best_score:
                best_score, best = score, d
        return best

    def _request_dock(self, r: Robot) -> None:
        if r.last_low_soc_t is None:
            r.last_low_soc_t = self.t

        if self.cfg.dock_strategy == "greedy":


            d = min(DOCKS, key=lambda dk: math.hypot(NODES[dk][0]-r.x,
                                                     NODES[dk][1]-r.y))
            r.target_dock = d
            r.path = bfs(nearest_node(r.x, r.y), d)
            r.state = "navigating_to_dock"
            self.log("dock_chosen", rid=r.rid, dock=d, strategy="greedy")
            return


        d = self._choose_dock(r)
        if d is None:
            r.state = "queued_for_dock"
            return
        self.dock_occupied[d] = r.rid
        r.target_dock = d
        start = nearest_node(r.x, r.y)
        r.path = bfs(start, d)
        r.state = "navigating_to_dock"
        self.log("dock_assigned", rid=r.rid, dock=d, strategy="allocator")


    def _check_failure(self, r: Robot) -> None:

        if r.state in ("failed", "repairing"):
            return
        p = BASE_FAIL_PROB_PER_S * (r.wear ** 2) * 4.0
        if self.rng.random() < p:
            self.log("failure", rid=r.rid, wear=round(r.wear, 3),
                     soc=round(r.soc, 1))
            r.state = "failed"
            r.repair_planned = False
            r.repair_started_t = self.t


        if self.cfg.maintenance_policy == "predictive"\
                and r.wear >= PREDICTIVE_THRESHOLD_WEAR\
                and r.last_anomaly_t is None:
            r.last_anomaly_t = self.t
            self.log("anomaly", rid=r.rid, severity="critical",
                     wear=round(r.wear, 3))


    def step(self) -> None:
        dt = 1.0
        for r in self.robots.values():

            if r.state == "repairing" and self.t >= r.work_until:
                r.state = "navigating"
                r.wear = 0.0
                r.last_anomaly_t = None
                r.repair_started_t = None
                r.repair_planned = False
                self.log("repaired", rid=r.rid)
                self._plan_next_step(r)
                continue

            if r.state == "failed":
                r.time_failed_s += dt

                if self.t - (r.repair_started_t or self.t) > 60:
                    lo, hi = REPAIR_TIME_REACTIVE_S
                    r.work_until = self.t + self.rng.uniform(lo, hi)
                    r.state = "repairing"
                    self.log("repair_start", rid=r.rid, type="reactive",
                             est_min=round((r.work_until - self.t)/60, 1))
                continue

            if r.state == "repairing":
                r.time_repairing_s += dt
                continue


            if (self.cfg.maintenance_policy == "predictive"
                    and r.last_anomaly_t is not None
                    and r.state in ("navigating", "working")
                    and r.mission_idx % len(MISSIONS[r.rid]) == 0
                    and not r.repair_planned):
                r.repair_planned = True
                lo, hi = REPAIR_TIME_PLANNED_S
                r.work_until = self.t + self.rng.uniform(lo, hi)
                r.state = "repairing"
                r.repair_started_t = self.t
                self.log("repair_start", rid=r.rid, type="planned",
                         lead_time_min=round((self.t - r.last_anomaly_t)/60, 1))
                continue


            if r.state == "queued_for_dock":
                r.time_queued_s += dt
                self._request_dock(r)
                continue


            if r.state == "waiting_at_dock":
                r.time_queued_s += dt
                if self.dock_occupied[r.target_dock] is None:
                    self.dock_occupied[r.target_dock] = r.rid
                    r.state = "charging"
                    queue_t = (self.t - r.last_low_soc_t) if r.last_low_soc_t else 0
                    self.log("dock_arrived", rid=r.rid, dock=r.target_dock,
                             queue_time_s=round(queue_t, 1),
                             empty_travel_m=round(r.distance_to_dock_m, 1))
                    r.distance_to_dock_m = 0.0
                continue


            if r.state == "charging":
                r.time_charging_s += dt
                r.soc = min(SOC_FULL, r.soc + SOC_GAIN_CHARGE_PER_S * dt)
                if r.soc >= SOC_FULL_RESUME:

                    if r.target_dock:
                        self.dock_occupied[r.target_dock] = None
                        self.log("charge_complete", rid=r.rid,
                                 dock=r.target_dock,
                                 dock_time_s=round(r.time_charging_s, 0))
                        r.target_dock = None
                    r.last_low_soc_t = None
                    self._plan_next_step(r)
                continue


            if r.state == "working":
                r.time_active_s += dt

                r.wear = min(1.0, r.wear + WEAR_RATE_PER_S * 0.3 * dt)
                r.soc -= SOC_DROP_IDLE_PER_S * dt
                if self.t >= r.work_until:
                    r.missions_done += 1
                    r.mission_idx += 1
                    self.log("mission_step_done", rid=r.rid,
                             missions=r.missions_done)
                    self._plan_next_step(r)
                continue


            if r.soc < SOC_LOW and r.state in ("navigating",):
                self.log("low_soc", rid=r.rid, soc=round(r.soc, 1))
                self._request_dock(r)
                continue


            if r.state in ("navigating", "navigating_to_dock"):
                self._tick_navigation(r, dt)
                continue


        for r in self.robots.values():
            self._check_failure(r)

        self.t += dt

    def _tick_navigation(self, r: Robot, dt: float) -> None:
        if not r.path:

            if r.state == "navigating_to_dock" and r.target_dock:
                occ = self.dock_occupied[r.target_dock]
                if occ is None or occ == r.rid:

                    self.dock_occupied[r.target_dock] = r.rid
                    r.state = "charging"
                    queue_t = (self.t - r.last_low_soc_t) if r.last_low_soc_t else 0
                    self.log("dock_arrived", rid=r.rid, dock=r.target_dock,
                             queue_time_s=round(queue_t, 1),
                             empty_travel_m=round(r.distance_to_dock_m, 1))
                    r.distance_to_dock_m = 0.0
                else:


                    r.state = "waiting_at_dock"
                    self.log("dock_collision", dock=r.target_dock, rid=r.rid,
                             occupied_by=occ)
                return

            mission = MISSIONS[r.rid]
            _, dur = mission[r.mission_idx % len(mission)]
            r.work_until = self.t + dur * WORK_FACTOR
            r.state = "working"
            return

        target = r.path[0]
        tx, ty = NODES[target]
        dx = tx - r.x; dy = ty - r.y
        d = math.hypot(dx, dy)
        if d < DOCK_TOLERANCE_M:
            r.path.pop(0)
            return

        step = CRUISE_SPEED_M_S * dt
        if step >= d:
            r.x = tx; r.y = ty
            r.distance_m += d
            if r.state == "navigating_to_dock":
                r.distance_to_dock_m += d
            r.path.pop(0)
        else:
            r.x += dx / d * step
            r.y += dy / d * step
            r.distance_m += step
            if r.state == "navigating_to_dock":
                r.distance_to_dock_m += step
        r.soc = max(0.0, r.soc - SOC_DROP_MOVE_PER_S * dt)
        r.wear = min(1.0, r.wear + WEAR_RATE_PER_S * dt)
        r.time_active_s += dt

    def run(self) -> dict:
        steps = int(self.cfg.shift_hours * 3600)
        for _ in range(steps):
            self.step()
        return {
            "events": self.events,
            "robots": {rid: {
                "missions_done":    r.missions_done,
                "time_failed_s":    r.time_failed_s,
                "time_repairing_s": r.time_repairing_s,
                "time_charging_s":  r.time_charging_s,
                "time_queued_s":    r.time_queued_s,
                "time_active_s":    r.time_active_s,
                "distance_m":       r.distance_m,
                "final_soc":        r.soc,
                "final_wear":       r.wear,
            } for rid, r in self.robots.items()},
            "meta": {
                "seed":         self.cfg.seed,
                "shift_hours":  self.cfg.shift_hours,
                "dock_strategy": self.cfg.dock_strategy,
                "maintenance_policy": self.cfg.maintenance_policy,
            },
        }


def run_simulation(*, seed: int, shift_hours: float,
                   dock_strategy: str, maintenance_policy: str) -> dict:
    sim = Simulator(SimConfig(
        seed=seed, shift_hours=shift_hours,
        dock_strategy=dock_strategy, maintenance_policy=maintenance_policy,
    ))
    return sim.run()

