"""Predictive-maintenance analytics.

These helpers produce the signals the engineering dashboard cares about
without needing a full ML stack:

  • ``component_health`` — derives a 0..100 health score for each hardware
    component from the most recent telemetry window.
  • ``rul_estimate`` — projects a remaining-useful-life (RUL) for a component
    via an exponential-fit model fed with SoH / temperature / vibration
    trends.  Good enough for demo & diploma; can be replaced by a proper
    ML model without breaking the API contract.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.robot import Robot, RobotComponent
from ..models.telemetry import TelemetrySnapshot
from ..schemas.predictive import (
    ComponentHealth, RulPrediction, SohForecast, SohForecastPoint,
)


BATTERY_HEALTHY_TEMP = 40.0
BATTERY_CRITICAL_TEMP = 55.0
MOTOR_HEALTHY_TEMP = 60.0
MOTOR_CRITICAL_TEMP = 90.0
MOTOR_HEALTHY_VIB = 0.25
MOTOR_CRITICAL_VIB = 1.2


SOH_REPLACEMENT_THRESHOLD = 70.0


RUL_REGRESSION_SAMPLES = 500
RUL_MIN_SAMPLES = 30
RUL_MIN_R2     = 0.25


def _window_avg(values: List[float]) -> float:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _trend_label(score: float) -> str:
    if score >= 85:
        return "stable"
    if score >= 65:
        return "degrading"
    if score >= 40:
        return "critical"
    return "critical"


async def component_health(db: AsyncSession, robot_id: UUID) -> list[ComponentHealth]:
    """Derive per-component health scores from the last ~5 minutes of telemetry."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    q = (
        select(TelemetrySnapshot)
        .where(TelemetrySnapshot.robot_id == robot_id,
               TelemetrySnapshot.recorded_at >= cutoff)
        .order_by(desc(TelemetrySnapshot.recorded_at))
        .limit(600)
    )
    rows = list((await db.execute(q)).scalars())
    components = list((await db.execute(
        select(RobotComponent).where(RobotComponent.robot_id == robot_id)
    )).scalars())

    avg_batt_temp  = _window_avg([r.battery_temp for r in rows])
    avg_soh        = _window_avg([r.battery_soh for r in rows])
    avg_left_temp  = _window_avg([r.left_motor_temp for r in rows])
    avg_right_temp = _window_avg([r.right_motor_temp for r in rows])
    avg_left_vib   = _window_avg([r.left_motor_vib for r in rows])
    avg_right_vib  = _window_avg([r.right_motor_vib for r in rows])

    out: list[ComponentHealth] = []
    for c in components:
        if c.category == "battery":
            temp_score = _linear_score(avg_batt_temp, BATTERY_HEALTHY_TEMP, BATTERY_CRITICAL_TEMP)
            soh_score  = max(0.0, min(100.0, avg_soh))
            health = 0.55 * soh_score + 0.45 * temp_score
            notes = (f"SoH={avg_soh:.1f}%, середня температура {avg_batt_temp:.1f}°C. "
                     + ("Деградація в межах норми." if health >= 80 else
                        "Прискорена деградація — рекомендовано провести діагностику балансування."))
        elif c.category == "motor":
            side = "left" if (c.position_label or "").startswith("left") else "right"
            temp = avg_left_temp if side == "left" else avg_right_temp
            vib  = avg_left_vib  if side == "left" else avg_right_vib
            temp_score = _linear_score(temp, MOTOR_HEALTHY_TEMP, MOTOR_CRITICAL_TEMP)
            vib_score  = _linear_score(vib,  MOTOR_HEALTHY_VIB,  MOTOR_CRITICAL_VIB)
            health = 0.55 * temp_score + 0.45 * vib_score
            notes = (f"T={temp:.1f}°C, vibration={vib:.2f} g. "
                     + ("Параметри в нормі." if health >= 80 else
                        "Виявлено підвищену вібрацію — ймовірно знос підшипника."))
        else:

            health = 90.0
            notes = "Нормальний стан (моніторинг базовий)."

        out.append(ComponentHealth(
            component_id=c.id,
            category=c.category,
            name=c.name,
            health_score=round(health, 1),
            soh_pct=c.current_soh_pct,
            degradation_trend=_trend_label(health),
            notes=notes,
        ))
    return out


def _linear_score(value: float, healthy: float, critical: float) -> float:
    """Map a sensor reading onto 0..100 (healthy=100, critical=0)."""
    if value <= healthy:
        return 100.0
    if value >= critical:
        return 0.0
    return (1.0 - (value - healthy) / (critical - healthy)) * 100.0


def _linear_regression(xs: List[float], ys: List[float]) -> Tuple[float, float, float]:
    """Ordinary least squares: повертає (slope, intercept, r2).

    Pure-Python без numpy/scipy, щоб не плодити залежності.  Точність ОК
    для наших ~500 точок і одновимірного y=ax+b.
    """
    n = len(xs)
    if n < 2:
        return 0.0, ys[0] if ys else 0.0, 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return 0.0, mean_y, 0.0
    slope = num / den
    intercept = mean_y - slope * mean_x

    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((ys[i] - (slope * xs[i] + intercept)) ** 2 for i in range(n))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    return slope, intercept, r2


def _downsample(rows: list, max_n: int) -> list:
    """Равномірна підвибірка не більше max_n елементів зі списку."""
    if len(rows) <= max_n:
        return rows
    step = len(rows) / max_n
    return [rows[int(i * step)] for i in range(max_n)]


async def soh_forecast(
    db: AsyncSession,
    robot_id: UUID,
    component_id: Optional[UUID] = None,
    threshold_pct: float = SOH_REPLACEMENT_THRESHOLD,
    horizon_days: int = 180,
) -> Optional[SohForecast]:
    """Побудувати лінійну регресію SoH за історією і спрогнозувати,
    через скільки днів він досягне порога заміни.

    Повертає None якщо точок недостатньо або тренд не значущий (R²<0.25).
    Якщо ``component_id`` не вказано — береться перша батарея робота.

    Часова шкала регресії — **дні з першої точки** (так slope зразу
    у читабельних одиницях "%/добу"), а не Unix-секунди — це уникає
    проблем з масштабуванням і нечитабельними intercept'ами.
    """

    if component_id is None:
        bat = (await db.execute(
            select(RobotComponent).where(RobotComponent.robot_id == robot_id,
                                          RobotComponent.category == "battery")
        )).scalars().first()
        if not bat:
            return None
        component_id = bat.id


    q = (select(TelemetrySnapshot.recorded_at, TelemetrySnapshot.battery_soh)
         .where(TelemetrySnapshot.robot_id == robot_id,
                TelemetrySnapshot.battery_soh.is_not(None))
         .order_by(TelemetrySnapshot.recorded_at))
    rows = (await db.execute(q)).all()
    if len(rows) < RUL_MIN_SAMPLES:
        return None

    rows = _downsample(rows, RUL_REGRESSION_SAMPLES)
    t0 = rows[0][0]
    xs = [(r[0] - t0).total_seconds() / 86400.0 for r in rows]
    ys = [float(r[1]) for r in rows]

    slope, intercept, r2 = _linear_regression(xs, ys)
    if r2 < RUL_MIN_R2 or slope >= 0:


        return None


    days_to_replacement: Optional[float] = None
    last_x = xs[-1]
    last_y = slope * last_x + intercept
    if last_y > threshold_pct:
        x_cross = (threshold_pct - intercept) / slope
        days_to_replacement = max(0.0, x_cross - last_x)


    history = [SohForecastPoint(t=rows[i][0], soh_pct=ys[i], is_forecast=False)
               for i in range(len(rows))]

    forecast: list[SohForecastPoint] = []
    step_days = max(1, horizon_days // 30)
    for d in range(step_days, horizon_days + 1, step_days):
        future_x = last_x + d
        soh = slope * future_x + intercept
        future_t = t0 + timedelta(days=future_x)
        forecast.append(SohForecastPoint(t=future_t,
                                          soh_pct=max(0.0, soh),
                                          is_forecast=True))
        if soh < 0:
            break

    return SohForecast(
        robot_id=robot_id,
        component_id=component_id,
        history=history,
        forecast=forecast,
        intercept_pct=round(intercept, 3),
        slope_pct_per_day=round(slope, 4),
        r2_score=round(r2, 4),
        replacement_threshold_pct=threshold_pct,
        days_to_replacement=(round(days_to_replacement, 1)
                              if days_to_replacement is not None else None),
        n_samples=len(rows),
    )


async def rul_estimates(db: AsyncSession, robot_id: UUID) -> list[RulPrediction]:
    """Estimate RUL for each component.

    Гібридна модель:
    * Для **батарей** — спочатку пробуємо лінійну регресію SoH (``soh_forecast``).
      Якщо тренд значущий (R²≥0.25 і slope<0), RUL обчислюємо як
      ``days_to_replacement * 24`` годин і помічаємо ``model='linear_regression'``.
      Інакше — fallback на евристику нижче.
    * Для **моторів** і всього іншого — евристика на основі очікуваного
      ресурсу і поточного health-фактора.
    """
    now = datetime.now(timezone.utc)
    components = list((await db.execute(
        select(RobotComponent).where(RobotComponent.robot_id == robot_id)
    )).scalars())
    healths = {h.component_id: h for h in await component_health(db, robot_id)}


    soh_fc = await soh_forecast(db, robot_id)

    out: list[RulPrediction] = []
    for c in components:
        life = c.expected_life_hours or 5000
        used = max(0, c.current_hours or 0)
        base_rul = max(0.0, life - used)
        h = healths.get(c.id)
        health_factor = max(0.1, (h.health_score / 100.0) if h else 0.9)

        model = "heuristic"
        r2 = None
        slope = None
        days_to_repl = None
        threshold = None
        predicted = base_rul * health_factor
        confidence = 0.55 + 0.35 * health_factor

        if c.category == "battery" and soh_fc and soh_fc.component_id == c.id:

            model = "linear_regression"
            r2 = soh_fc.r2_score
            slope = soh_fc.slope_pct_per_day
            days_to_repl = soh_fc.days_to_replacement
            threshold = soh_fc.replacement_threshold_pct
            if days_to_repl is not None:
                predicted = round(days_to_repl * 24.0, 1)

            confidence = round(0.55 + 0.40 * min(1.0, r2), 2)
            recommendation = (
                f"Лінійна регресія SoH: тренд {slope:+.3f}%/добу, R²={r2:.2f}. "
                + (f"Прогнозований ресурс до заміни — {days_to_repl:.0f} днів."
                   if days_to_repl is not None else
                   "Поточний рівень вище порога заміни.")
            )
        elif c.category == "battery":
            recommendation = (
                "Продовжити експлуатацію; планова перевірка через квартал."
                if health_factor > 0.8 else
                "Запланувати заміну батареї протягом найближчих 60 днів."
            )
        elif c.category == "motor":
            recommendation = (
                "Продовжити експлуатацію."
                if health_factor > 0.8 else
                "Призначити огляд підшипника та редуктора; можлива заміна."
            )
        else:
            recommendation = "Підтримувати плановий графік ТО."

        out.append(RulPrediction(
            robot_id=robot_id,
            component_id=c.id,
            component_name=c.name,
            predicted_rul_hours=round(predicted, 1),
            confidence=round(confidence, 2),
            recommendation=recommendation,
            predicted_at=now,
            model=model,
            r2_score=r2,
            soh_slope_pct_per_day=slope,
            days_to_replacement=days_to_repl,
            replacement_threshold_pct=threshold,
        ))
    return out


async def fleet_health_summary(db: AsyncSession) -> list[Tuple[UUID, str, float]]:
    """Compute a single 0..100 health score per robot (MIN of component scores)."""
    robots = list((await db.execute(select(Robot))).scalars())
    summary = []
    for r in robots:
        healths = await component_health(db, r.id)
        score = min((h.health_score for h in healths), default=100.0)
        summary.append((r.id, r.code, score))
    return summary
