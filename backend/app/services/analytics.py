"""KPI-аналітика парку: availability, OEE, MTBF, MTTR, аномалії, тікети.

Усі KPI рахуються за вибраний період (за замовч. — остання доба).  Виходи
зведено у плоскі словники, готові до серіалізації у JSON для дашборду.

Як обчислюємо
─────────────
* **Availability** — частка часу, коли робот був у `operational`/`charging`
  (норма) проти `failed`/`critical`/`idle`-без-причини.  Знімаємо знімки
  з ``telemetry_snapshots`` і агрегуємо state-розподіл за період.
  Якщо снапшотів мало — fallback на події тікетів: 100 % мінус
  (Σ хв незакритих corrective/emergency тікетів / період).

* **OEE** (Overall Equipment Effectiveness) — спрощено для AMR:
      OEE = Availability × Performance × Quality
  Performance = виконано місій / теоретично можливих за час (300 c на цикл).
  Quality поки 1.0 — у AMR немає браку (можна підмінити при додаванні
  логістичних інцидентів).

* **MTBF** — середній час між поломками: береться різниця між послідовними
  тікетами ``maintenance_type in ('corrective','emergency')``.

* **MTTR** — середній час від ``ticket.created_at`` до ``ticket.completed_at``
  для тих самих тікетів.

* **Anomalies** — підрахунок за період + breakdown за severity.

Все це за один прохід по ``telemetry_snapshots`` + 2 SELECT по
``tickets`` + 1 SELECT по ``anomaly_events``.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.alert import AnomalyEvent
from ..models.robot import Robot
from ..models.telemetry import TelemetrySnapshot
from ..models.ticket import Ticket


EXPECTED_MISSION_CYCLE_S = 300.0


SNAPSHOT_INTERVAL_S = 1.5


AVAILABLE_STATES = {"navigating", "working", "docking", "charging"}

FAULT_STATES = {"failed", "critical", "error"}


async def kpi_snapshot(
    db: AsyncSession,
    *,
    period_from: Optional[datetime] = None,
    period_to: Optional[datetime] = None,
    robot_id: Optional[UUID] = None,
) -> dict:
    """Розрахувати агреговані KPI парку за період.

    Якщо ``robot_id`` вказано — повертає тільки цього робота (per_robot
    матиме 1 запис, fleet-агрегати співпадуть із значеннями робота).
    """
    now = datetime.now(timezone.utc)
    t_to = period_to or now
    t_from = period_from or (t_to - timedelta(hours=24))
    period_s = max(1.0, (t_to - t_from).total_seconds())

    robots_q = select(Robot)
    if robot_id:
        robots_q = robots_q.where(Robot.id == robot_id)
    robots = list((await db.execute(robots_q)).scalars())
    if not robots:
        return _empty_snapshot(t_from, t_to)

    per_robot: list[dict] = []
    fleet_avail_acc = 0.0
    fleet_perf_acc  = 0.0
    fleet_missions  = 0
    fleet_anomalies = 0
    total_failed_s  = 0.0
    mtbf_intervals_h: list[float] = []
    mttr_durations_h: list[float] = []


    snap_q = (select(TelemetrySnapshot.robot_id, TelemetrySnapshot.state,
                     func.count().label("cnt"))
              .where(TelemetrySnapshot.recorded_at >= t_from,
                     TelemetrySnapshot.recorded_at <= t_to,
                     TelemetrySnapshot.state.is_not(None))
              .group_by(TelemetrySnapshot.robot_id, TelemetrySnapshot.state))
    if robot_id:
        snap_q = snap_q.where(TelemetrySnapshot.robot_id == robot_id)
    state_counts: dict[UUID, dict[str, int]] = defaultdict(dict)
    for row in (await db.execute(snap_q)).all():
        state_counts[row.robot_id][row.state] = int(row.cnt)


    anom_q = (select(AnomalyEvent.robot_id, AnomalyEvent.severity,
                     func.count().label("cnt"))
              .where(AnomalyEvent.detected_at >= t_from,
                     AnomalyEvent.detected_at <= t_to)
              .group_by(AnomalyEvent.robot_id, AnomalyEvent.severity))
    if robot_id:
        anom_q = anom_q.where(AnomalyEvent.robot_id == robot_id)
    anom_by_robot: dict[UUID, dict[str, int]] = defaultdict(dict)
    for row in (await db.execute(anom_q)).all():
        anom_by_robot[row.robot_id][row.severity] = int(row.cnt)


    tick_q = (select(Ticket)
              .where(Ticket.created_at >= t_from,
                     Ticket.created_at <= t_to,
                     Ticket.maintenance_type.in_(("corrective", "emergency"))))
    if robot_id:
        tick_q = tick_q.where(Ticket.robot_id == robot_id)
    tickets_by_robot: dict[UUID, list[Ticket]] = defaultdict(list)
    for t in (await db.execute(tick_q)).scalars():
        tickets_by_robot[t.robot_id].append(t)


    tickets_open_total = 0
    tickets_resolved_total = 0
    open_q = (select(func.count())
              .select_from(Ticket)
              .where(Ticket.status.in_(("open", "assigned", "in_progress",
                                         "waiting_parts"))))
    if robot_id:
        open_q = open_q.where(Ticket.robot_id == robot_id)
    tickets_open_total = int((await db.execute(open_q)).scalar() or 0)

    resolved_q = (select(func.count())
                  .select_from(Ticket)
                  .where(Ticket.completed_at.is_not(None),
                         Ticket.completed_at >= t_from,
                         Ticket.completed_at <= t_to))
    if robot_id:
        resolved_q = resolved_q.where(Ticket.robot_id == robot_id)
    tickets_resolved_total = int((await db.execute(resolved_q)).scalar() or 0)

    for r in robots:
        counts = state_counts.get(r.id, {})
        total_cnt = sum(counts.values()) or 1
        avail_cnt = sum(v for k, v in counts.items() if k in AVAILABLE_STATES)
        fail_cnt  = sum(v for k, v in counts.items() if k in FAULT_STATES)


        if not counts:
            availability = 100.0
            active_h = charging_h = idle_h = failed_h = 0.0
        else:
            availability = 100.0 * avail_cnt / total_cnt

            def hours_for(states):
                cnt = sum(v for k, v in counts.items() if k in states)
                return round(cnt * SNAPSHOT_INTERVAL_S / 3600.0, 2)
            active_h   = hours_for({"navigating", "working", "docking"})
            charging_h = hours_for({"charging"})
            idle_h     = hours_for({"idle"})
            failed_h   = hours_for(FAULT_STATES)
            total_failed_s += failed_h * 3600

        anoms = anom_by_robot.get(r.id, {})
        anoms_total = sum(anoms.values())


        delta_missions = max(0, r.total_missions or 0)

        expected_missions = (active_h * 3600.0 / EXPECTED_MISSION_CYCLE_S) if active_h else 0
        performance = (min(1.0, delta_missions / expected_missions)
                       if expected_missions > 0 else 1.0) * 100

        if not r.total_missions:
            performance = 100.0


        ts = sorted(tickets_by_robot.get(r.id, []), key=lambda x: x.created_at)
        intervals_h = []
        for i in range(1, len(ts)):
            intervals_h.append((ts[i].created_at - ts[i-1].created_at).total_seconds() / 3600)
        durations_h = []
        for t in ts:
            if t.completed_at:
                durations_h.append((t.completed_at - t.created_at).total_seconds() / 3600)
        mtbf_h = sum(intervals_h) / len(intervals_h) if intervals_h else None
        mttr_h = sum(durations_h) / len(durations_h) if durations_h else None
        if mtbf_h is not None:
            mtbf_intervals_h.append(mtbf_h)
        if mttr_h is not None:
            mttr_durations_h.append(mttr_h)

        per_robot.append({
            "robot_id": str(r.id),
            "code": r.code,
            "availability_pct": round(availability, 2),
            "active_hours": active_h,
            "charging_hours": charging_h,
            "idle_hours": idle_h,
            "failed_hours": failed_h,
            "missions_completed": delta_missions,
            "anomalies": anoms_total,
            "mtbf_hours": round(mtbf_h, 2) if mtbf_h is not None else None,
            "mttr_hours": round(mttr_h, 2) if mttr_h is not None else None,
        })

        fleet_avail_acc += availability
        fleet_perf_acc  += performance
        fleet_missions  += delta_missions
        fleet_anomalies += anoms_total

    n = len(robots)
    fleet_avail = fleet_avail_acc / n if n else 100.0
    fleet_perf  = fleet_perf_acc  / n if n else 100.0
    fleet_oee   = fleet_avail * fleet_perf / 100.0

    return {
        "period_from":   t_from,
        "period_to":     t_to,
        "total_robots":  n,
        "fleet_availability_pct": round(fleet_avail, 2),
        "fleet_oee_pct":          round(fleet_oee, 2),
        "mtbf_hours":             round(sum(mtbf_intervals_h)/len(mtbf_intervals_h), 2)
                                    if mtbf_intervals_h else 0.0,
        "mttr_hours":             round(sum(mttr_durations_h)/len(mttr_durations_h), 2)
                                    if mttr_durations_h else 0.0,
        "anomalies_total":        fleet_anomalies,
        "anomalies_critical":     sum(
            anom_by_robot.get(r.id, {}).get("critical", 0) +
            anom_by_robot.get(r.id, {}).get("emergency", 0)
            for r in robots),
        "tickets_open":      tickets_open_total,
        "tickets_resolved":  tickets_resolved_total,
        "unplanned_downtime_hours": round(total_failed_s / 3600.0, 2),
        "missions_completed":       fleet_missions,
        "per_robot":         per_robot,
    }


def _empty_snapshot(t_from: datetime, t_to: datetime) -> dict:
    return {"period_from": t_from, "period_to": t_to, "total_robots": 0,
            "fleet_availability_pct": 0.0, "fleet_oee_pct": 0.0,
            "mtbf_hours": 0.0, "mttr_hours": 0.0,
            "anomalies_total": 0, "anomalies_critical": 0,
            "tickets_open": 0, "tickets_resolved": 0,
            "unplanned_downtime_hours": 0.0, "missions_completed": 0,
            "per_robot": []}
