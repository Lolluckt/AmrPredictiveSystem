"""Запуск матриці експериментів і збереження результатів у CSV.

Запуск:
    python run_experiment.py --runs 30 --shift-hours 8 --seed 42 --out results/

Алгоритм:
    Для кожного seed від ``seed`` до ``seed+runs-1`` запускаємо 4 конфігурації:
        (greedy + reactive)        ← повний baseline ("ні нашого рішення")
        (allocator + reactive)     ← лише dock allocator
        (greedy + predictive)      ← лише predictive maintenance
        (allocator + predictive)   ← запропоноване повне рішення
    Це дозволяє у звіті розкласти внесок кожної компоненти ("ablation").

Виходи (results/):
    runs.csv         — один рядок = один прогон, з усіма KPI
    summary.csv      — агрегати mean/std/CI на configuration × strategy
    charts/*.png     — bar/box-діаграми по ключових KPI
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from pathlib import Path
from statistics import mean, stdev
from typing import List


sys.path.insert(0, os.path.dirname(__file__))

from metrics import kpi_for_run
from sim import run_simulation

CONFIGS = [
    ("greedy",    "reactive",    "Baseline (старе)"),
    ("allocator", "reactive",    "+ Allocator only"),
    ("greedy",    "predictive",  "+ Predictive only"),
    ("allocator", "predictive",  "Запропоноване (повне)"),
]

CHART_METRICS = [
    ("availability_pct",            "Доступність флоту, %"),
    ("missions_total",              "Виконано місій / зміну"),
    ("unplanned_downtime_pct",      "Незапланований простій, %"),
    ("mttr_h",                      "MTTR, год"),
    ("dock_queue_time_s_avg",       "Сер. час черги на док, с"),
    ("empty_travel_to_dock_m_avg",  "Сер. порожній пробіг до дока, м"),
    ("dock_collisions",             "Колізій на доках за зміну"),
    ("predictive_lead_time_min",    "Lead time детекції, хв"),
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=30,
                   help="Кількість прогонів на кожну конфігурацію")
    p.add_argument("--shift-hours", type=float, default=8.0,
                   help="Тривалість симуляції (год)")
    p.add_argument("--seed", type=int, default=42, help="Базовий seed")
    p.add_argument("--out", type=str, default="results", help="Куди писати CSV")
    return p.parse_args()


def _ci95(xs: List[float]) -> float:
    """95% довірчий інтервал для середнього (нормальне наближення)."""
    if len(xs) < 2:
        return 0.0
    return 1.96 * (stdev(xs) / math.sqrt(len(xs)))


def main():
    args = parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    charts_dir = out / "charts"
    charts_dir.mkdir(exist_ok=True)

    print(f"== Запуск {args.runs} × {len(CONFIGS)} = "
          f"{args.runs*len(CONFIGS)} прогонів × {args.shift_hours} год ==")

    rows: List[dict] = []
    for dock, maint, label in CONFIGS:
        for i in range(args.runs):
            seed = args.seed + i
            res = run_simulation(seed=seed, shift_hours=args.shift_hours,
                                 dock_strategy=dock, maintenance_policy=maint)
            kpi = kpi_for_run(res)
            kpi["config_label"] = label
            rows.append(kpi)

        last = rows[-1]
        print(f"  [{label}] last run #{args.runs}: "
              f"availability={last['availability_pct']}%  "
              f"missions={last['missions_total']}  "
              f"downtime={last['unplanned_downtime_pct']}%")


    runs_csv = out / "runs.csv"
    with runs_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"→ {runs_csv}")


    summary_rows = []
    metrics_to_summarize = [k for k in rows[0].keys()
                            if k not in ("dock_strategy","maintenance_policy",
                                         "seed","shift_hours","config_label")]
    for dock, maint, label in CONFIGS:
        subset = [r for r in rows if r["dock_strategy"] == dock
                  and r["maintenance_policy"] == maint]
        row = {"config_label": label,
               "dock_strategy": dock, "maintenance_policy": maint,
               "n": len(subset)}
        for m in metrics_to_summarize:
            xs = [r[m] for r in subset]
            row[f"{m}_mean"] = round(mean(xs), 3)
            row[f"{m}_ci95"] = round(_ci95(xs), 3)
        summary_rows.append(row)
    summary_csv = out / "summary.csv"
    with summary_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)
    print(f"→ {summary_csv}")


    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("WARN: matplotlib не встановлено — пропускаю графіки. "
              "pip install matplotlib")
        return

    labels = [c[2] for c in CONFIGS]
    for metric, title in CHART_METRICS:
        means = []; cis = []
        for dock, maint, _ in CONFIGS:
            xs = [r[metric] for r in rows
                  if r["dock_strategy"] == dock
                  and r["maintenance_policy"] == maint]
            means.append(mean(xs))
            cis.append(_ci95(xs))
        fig, ax = plt.subplots(figsize=(7, 4))
        x = list(range(len(labels)))
        bars = ax.bar(x, means, yerr=cis, capsize=4,
                      color=["#9CA3AF","#60A5FA","#34D399","#F59E0B"])
        ax.set_xticks(x); ax.set_xticklabels(labels, rotation=15, ha="right")
        ax.set_title(title)
        ax.set_ylabel(title)
        for b, m in zip(bars, means):
            ax.text(b.get_x()+b.get_width()/2, b.get_height(),
                    f"{m:.2f}", ha="center", va="bottom", fontsize=8)
        fig.tight_layout()
        fig.savefig(charts_dir / f"{metric}.png", dpi=120)
        plt.close(fig)
    print(f"→ {charts_dir}/*.png ({len(CHART_METRICS)} графіків)")


    print("\n== Підсумок (середні) ==")
    print(f"{'Конфігурація':30s}  avail%   місій  downtime%  колізій  черга_c")
    for r in summary_rows:
        print(f"  {r['config_label']:28s} "
              f"{r['availability_pct_mean']:6.2f}  "
              f"{r['missions_total_mean']:6.1f}  "
              f"{r['unplanned_downtime_pct_mean']:8.2f}  "
              f"{r['dock_collisions_mean']:6.1f}  "
              f"{r['dock_queue_time_s_avg_mean']:7.1f}")


if __name__ == "__main__":
    main()
