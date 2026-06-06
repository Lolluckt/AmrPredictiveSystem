"""Telemetry readout + HTTP fallback ingest + CSV/XLSX export."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..core.deps import require_permission
from ..core.roles import Permission
from ..db import get_session
from ..models.robot import Robot
from ..models.telemetry import TelemetrySnapshot
from ..models.user import User
from ..schemas.telemetry import (
    TelemetryIngestIn, TelemetryOut, TelemetrySeriesPoint,
)
from ..services.anomaly import evaluate_snapshot
from ..services.event_bus import bus

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


EXPORT_COLUMNS = [
    "recorded_at", "robot_code", "zone", "pos_x", "pos_y", "heading_deg",
    "state", "mission_step", "odometry_m",
    "battery_soc", "battery_soh", "battery_voltage", "battery_current",
    "battery_temp", "battery_internal_r",
    "left_motor_temp", "right_motor_temp",
    "left_motor_vib", "right_motor_vib",
    "left_motor_eff", "right_motor_eff",
]


@router.get("/{robot_id}/latest", response_model=TelemetryOut | None)
async def latest(
    robot_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.TELEMETRY_VIEW)),
) -> TelemetrySnapshot | None:
    q = (select(TelemetrySnapshot)
         .where(TelemetrySnapshot.robot_id == robot_id)
         .order_by(TelemetrySnapshot.recorded_at.desc())
         .limit(1))
    return (await db.execute(q)).scalar_one_or_none()


@router.get("/latest", response_model=list[TelemetryOut])
async def latest_per_robot(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.TELEMETRY_VIEW)),
) -> list[TelemetrySnapshot]:
    """One latest row per robot — used by the dashboard map in a single fetch."""
    sub = (select(TelemetrySnapshot.robot_id,
                  func.max(TelemetrySnapshot.recorded_at).label("mx"))
           .group_by(TelemetrySnapshot.robot_id)
           .subquery())
    s2 = aliased(TelemetrySnapshot)
    q = (select(s2)
         .join(sub, (s2.robot_id == sub.c.robot_id)
                    & (s2.recorded_at == sub.c.mx))
         .order_by(s2.robot_id))
    return list((await db.execute(q)).scalars())


@router.get("/{robot_id}/history", response_model=list[TelemetryOut])
async def history(
    robot_id: UUID,
    limit: int = Query(200, ge=1, le=2000),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.TELEMETRY_VIEW)),
) -> list[TelemetrySnapshot]:
    q = (select(TelemetrySnapshot)
         .where(TelemetrySnapshot.robot_id == robot_id)
         .order_by(TelemetrySnapshot.recorded_at.desc())
         .limit(limit))
    return list((await db.execute(q)).scalars())


SeriesKey = Literal[
    "battery_soc", "battery_soh", "battery_temp", "battery_voltage",
    "left_motor_temp", "right_motor_temp",
    "left_motor_vib", "right_motor_vib",
    "odometry_m",
]


@router.get("/{robot_id}/series", response_model=list[TelemetrySeriesPoint])
async def series(
    robot_id: UUID,
    field: SeriesKey,
    limit: int = Query(300, ge=1, le=2000),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.TELEMETRY_VIEW)),
) -> list[TelemetrySeriesPoint]:
    col = getattr(TelemetrySnapshot, field)
    q = (select(TelemetrySnapshot.recorded_at, col)
         .where(TelemetrySnapshot.robot_id == robot_id, col.is_not(None))
         .order_by(desc(TelemetrySnapshot.recorded_at))
         .limit(limit))
    rows = (await db.execute(q)).all()
    rows.reverse()
    return [TelemetrySeriesPoint(t=r[0], value=float(r[1])) for r in rows]


async def _stream_csv(rows_iter, robot_code: str):
    """Async-генератор стрічечок CSV.  Стрімимо щоб не тримати все в пам'яті."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_COLUMNS)
    yield buf.getvalue(); buf.seek(0); buf.truncate(0)
    async for snap in rows_iter:
        writer.writerow([
            snap.recorded_at.isoformat(), robot_code, snap.zone,
            snap.pos_x, snap.pos_y, snap.heading_deg,
            snap.state, snap.mission_step, snap.odometry_m,
            snap.battery_soc, snap.battery_soh, snap.battery_voltage,
            snap.battery_current, snap.battery_temp, snap.battery_internal_r,
            snap.left_motor_temp, snap.right_motor_temp,
            snap.left_motor_vib, snap.right_motor_vib,
            snap.left_motor_eff, snap.right_motor_eff,
        ])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)


@router.get("/{robot_id}/export")
async def export_telemetry(
    robot_id: UUID,
    from_: Optional[datetime] = Query(None, alias="from",
        description="ISO datetime; за замовч. — 24 год тому"),
    to: Optional[datetime] = None,
    format: Literal["csv", "xlsx"] = Query("csv"),
    max_rows: int = Query(50_000, ge=100, le=500_000),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.TELEMETRY_VIEW)),
):
    """Експорт телеметрії у CSV або XLSX за вибраний період.

    CSV стрімиться чанками — не блокує event loop і не тримає всі рядки
    у пам'яті, тому можна викачувати сотні тисяч точок.
    XLSX будується через ``openpyxl`` (якщо встановлений), бо стрімити
    у XLSX не можна — це формат, що не підтримує append на льоту.

    Зразок:
        GET /api/telemetry/<id>/export?from=2026-05-18T00:00:00Z
                                     &to=2026-05-19T00:00:00Z&format=csv
    """
    robot = await db.get(Robot, robot_id)
    if not robot:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Робота не знайдено")

    now = datetime.now(timezone.utc)
    t_to = to or now
    t_from = from_ or (t_to - timedelta(hours=24))
    if t_from >= t_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "from має бути < to")

    q = (select(TelemetrySnapshot)
         .where(TelemetrySnapshot.robot_id == robot_id,
                TelemetrySnapshot.recorded_at >= t_from,
                TelemetrySnapshot.recorded_at <= t_to)
         .order_by(asc(TelemetrySnapshot.recorded_at))
         .limit(max_rows))

    fname_safe = robot.code.replace("/", "_")
    fname_period = f"{t_from.strftime('%Y%m%d_%H%M')}-{t_to.strftime('%Y%m%d_%H%M')}"
    fname_base = f"telemetry_{fname_safe}_{fname_period}"

    if format == "csv":
        async def _rows():
            res = await db.stream(q)
            async for row in res:
                yield row[0]
        return StreamingResponse(
            _stream_csv(_rows(), robot.code),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="{fname_base}.csv"'},
        )


    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "Експорт у XLSX недоступний: відсутній openpyxl. "
            "Встановіть `pip install openpyxl` або скористайтеся ?format=csv.",
        )
    rows = list((await db.execute(q)).scalars())
    wb = Workbook()
    ws = wb.active
    ws.title = robot.code
    ws.append(EXPORT_COLUMNS)
    for snap in rows:
        ws.append([
            snap.recorded_at.replace(tzinfo=None), robot.code, snap.zone,
            snap.pos_x, snap.pos_y, snap.heading_deg,
            snap.state, snap.mission_step, snap.odometry_m,
            snap.battery_soc, snap.battery_soh, snap.battery_voltage,
            snap.battery_current, snap.battery_temp, snap.battery_internal_r,
            snap.left_motor_temp, snap.right_motor_temp,
            snap.left_motor_vib, snap.right_motor_vib,
            snap.left_motor_eff, snap.right_motor_eff,
        ])

    for i, _ in enumerate(EXPORT_COLUMNS, start=1):
        col = ws.column_dimensions[chr(64 + i) if i <= 26 else "A" + chr(64 + i - 26)]
        col.width = 16
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="{fname_base}.xlsx"'},
    )


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    payload: TelemetryIngestIn,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_permission(Permission.TELEMETRY_VIEW)),
) -> dict:
    """HTTP fallback when MQTT is not available (for CI / tests).

    Production path is backend/services/mqtt_ingest.py (paho-mqtt loop)."""
    q = await db.execute(select(Robot).where(Robot.code == payload.robot_code))
    robot = q.scalar_one_or_none()
    if not robot:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Робота не знайдено")

    data = payload.model_dump(exclude={"robot_code"})
    if not data.get("recorded_at"):
        data["recorded_at"] = datetime.now(timezone.utc)
    snap = TelemetrySnapshot(robot_id=robot.id, **data)
    db.add(snap)
    if snap.pos_x is not None:
        robot.last_x = snap.pos_x; robot.last_y = snap.pos_y
        robot.last_heading_deg = snap.heading_deg
        robot.last_zone = snap.zone
    robot.last_seen_at = snap.recorded_at
    await db.flush()
    events = await evaluate_snapshot(db, robot.id, snap)
    await db.commit()


    bus.publish("telemetry", "update", robot_id=robot.id,
                data={"robot_id": str(robot.id), "robot_code": robot.code,
                      "ts": snap.recorded_at.isoformat(),
                      "pos_x": snap.pos_x, "pos_y": snap.pos_y,
                      "battery_soc": snap.battery_soc,
                      "battery_temp": snap.battery_temp,
                      "left_motor_temp": snap.left_motor_temp,
                      "right_motor_temp": snap.right_motor_temp,
                      "state": snap.state})
    for ev in events:
        bus.publish("anomaly", "create", robot_id=robot.id, entity_id=ev.id,
                    data={"id": str(ev.id), "robot_id": str(ev.robot_id),
                          "severity": ev.severity, "parameter": ev.parameter,
                          "value": ev.value, "threshold": ev.threshold,
                          "message": ev.message,
                          "detected_at": ev.detected_at.isoformat()})

    return {"accepted": True, "snapshot_id": str(snap.id),
            "anomalies": len(events)}
