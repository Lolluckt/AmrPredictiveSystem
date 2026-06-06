"""Обчислення KPI з event-log одного прогону симуляції."""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, median
from typing import Dict, List


def kpi_for_run(result: dict) -> dict:
    """Перетворити вихід ``Simulator.run`` у плоский словник KPI."""
    events: List[dict] = result["events"]
    robots: Dict[str, dict] = result["robots"]
    meta: dict = result["meta"]
    shift_s = meta["shift_hours"] * 3600


    missions_total = sum(r["missions_done"] for r in robots.values())
    missions_per_robot = mean(r["missions_done"] for r in robots.values())
    n_robots = len(robots)


    avg_failed   = mean(r["time_failed_s"]    for r in robots.values())
    avg_repair   = mean(r["time_repairing_s"] for r in robots.values())
    avg_charging = mean(r["time_charging_s"]  for r in robots.values())
    avg_queued   = mean(r["time_queued_s"]    for r in robots.values())
    avg_active   = mean(r["time_active_s"]    for r in robots.values())

    availability_pct = 100.0 * (shift_s - avg_failed - avg_repair - avg_queued) / shift_s


    dock_collisions = sum(1 for ev in events if ev["kind"] == "dock_collision")


    failures = [ev for ev in events if ev["kind"] == "failure"]
    repairs  = [ev for ev in events if ev["kind"] == "repair_start"]
    unplanned_repairs = [ev for ev in repairs if ev["type"] == "reactive"]
    planned_repairs   = [ev for ev in repairs if ev["type"] == "planned"]


    fails_by_robot = defaultdict(list)
    for ev in failures:
        fails_by_robot[ev["rid"]].append(ev["t"])
    inter_failure_h = []
    for ts in fails_by_robot.values():
        for i in range(1, len(ts)):
            inter_failure_h.append((ts[i] - ts[i-1]) / 3600)
    mtbf_h = mean(inter_failure_h) if inter_failure_h else (shift_s / 3600)


    repairs_by_rid = defaultdict(list)
    for ev in events:
        if ev["kind"] in ("repair_start", "repaired"):
            repairs_by_rid[ev["rid"]].append(ev)
    durations_h = []
    for rid, evs in repairs_by_rid.items():
        for i in range(len(evs) - 1):
            if evs[i]["kind"] == "repair_start" and evs[i+1]["kind"] == "repaired":
                durations_h.append((evs[i+1]["t"] - evs[i]["t"]) / 3600)
    mttr_h = mean(durations_h) if durations_h else 0.0


    lead_times = [ev["lead_time_min"] for ev in planned_repairs
                  if "lead_time_min" in ev]
    lead_time_avg = mean(lead_times) if lead_times else 0.0


    queue_times = []
    travel_to_dock_m = []
    for ev in events:
        if ev["kind"] == "dock_arrived":
            queue_times.append(ev.get("queue_time_s", 0))
            travel_to_dock_m.append(ev.get("empty_travel_m", 0))
    dock_queue_avg_s = mean(queue_times) if queue_times else 0.0


    dock_queue_med_s = median(queue_times) if queue_times else 0.0
    empty_travel_avg = mean(travel_to_dock_m) if travel_to_dock_m else 0.0


    anomaly_evs = [ev for ev in events if ev["kind"] == "anomaly"]
    fp = 0
    for ae in anomaly_evs:
        had_failure = any(fe["rid"] == ae["rid"]
                          and 0 <= fe["t"] - ae["t"] <= 3600
                          for fe in failures)

        had_planned = any(pr["rid"] == ae["rid"]
                          and 0 <= pr["t"] - ae["t"] <= 3600
                          for pr in planned_repairs)
        if not had_failure and not had_planned:
            fp += 1
    fp_rate = fp / len(anomaly_evs) if anomaly_evs else 0.0

    return {
        "dock_strategy":        meta["dock_strategy"],
        "maintenance_policy":   meta["maintenance_policy"],
        "seed":                 meta["seed"],
        "shift_hours":          meta["shift_hours"],
        "missions_total":       missions_total,
        "missions_per_robot":   round(missions_per_robot, 2),
        "availability_pct":     round(availability_pct, 2),
        "avg_active_s":         round(avg_active, 0),
        "avg_charging_s":       round(avg_charging, 0),
        "avg_queued_s":         round(avg_queued, 0),
        "avg_failed_s":         round(avg_failed, 0),
        "avg_repair_s":         round(avg_repair, 0),
        "unplanned_downtime_pct": round(100.0 * (avg_failed + avg_repair) / shift_s, 2),
        "mtbf_h":               round(mtbf_h, 2),
        "mttr_h":               round(mttr_h, 2),
        "n_failures":           len(failures),
        "n_planned_repairs":    len(planned_repairs),
        "n_unplanned_repairs":  len(unplanned_repairs),
        "n_anomalies":          len(anomaly_evs),
        "predictive_lead_time_min": round(lead_time_avg, 1),
        "false_positive_rate":  round(fp_rate, 3),
        "dock_queue_time_s_avg": round(dock_queue_avg_s, 1),
        "dock_queue_time_s_median": round(dock_queue_med_s, 1),
        "unplanned_failures": len(failures),
        "empty_travel_to_dock_m_avg": round(empty_travel_avg, 1),
        "dock_collisions":      dock_collisions,
    }
