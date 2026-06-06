"""Bootstrap development data.

Run with:
    python -m app.seed

Idempotent: safe to run multiple times.  Creates tables if missing,
inserts 3 demo users (1 per role), 1 factory/line with the 9 zones that
match the Webots world, 3 AMRs with a full component list, 4 starter
alert rules, and 1 demo predictive-maintenance ticket.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .core.security import hash_password
from .db import Base, SessionLocal, engine
from .models.alert import AlertRule, AnomalyEvent
from .models.factory import ChargingStation, Factory, ProductionLine, WorkshopZone
from .models.mission import Mission
from .models.robot import Robot, RobotComponent
from .models.ticket import Ticket
from .models.user import User


ZONES = [

    ("Склад сировини", "warehouse", "#6366F1", 0, 0, 10, 9),
    ("Коридор (головний)", "corridor", "#6B7280", 10, 0, 13, 24),
    ("Ділянка збирання A", "assembly", "#10B981", 13, 0, 23, 9),
    ("Коридор (поперечний)", "corridor", "#6B7280", 0, 9, 40, 11),
    ("Ділянка збирання B", "assembly", "#10B981", 13, 11, 23, 24),
    ("Зона зварювання", "welding", "#F59E0B", 23, 0, 32, 9),
    ("Зона пакування", "packaging", "#EC4899", 23, 11, 32, 24),
    ("Зона зарядки", "charging_area", "#3B82F6", 0, 11, 10, 15),
    ("Контроль якості", "quality_control", "#8B5CF6", 0, 15, 10, 24),
    ("Склад готової продукції", "warehouse", "#6366F1", 32, 0, 40, 24),
]

CHARGERS = [("CS-01", 2.0, 13.0), ("CS-02", 5.0, 13.0), ("CS-03", 8.0, 13.0)]

ROBOTS_SEED = [

    ("AMR-01", "SN-AMR100X-00001", "AMR-100X", "amr_01_client", "operational", 5.0, 4.5),
    ("AMR-02", "SN-AMR100X-00002", "AMR-100X", "amr_02_client", "operational", 18.0, 4.5),
    ("AMR-03", "SN-AMR100X-00003", "AMR-100X", "amr_03_client", "idle",        5.0, 19.5),
]

COMPONENTS_PER_ROBOT = [
    ("battery", "Батарея Li-Ion 48V 20Ah", "main_battery", "BAT-LI48-20", 87.5, 3000, 820),
    ("motor",   "Лівий тяговий двигун BLDC",  "left_wheel",   "MOT-BLDC-200W", None, 5000, 820),
    ("motor",   "Правий тяговий двигун BLDC", "right_wheel",  "MOT-BLDC-200W", None, 5000, 820),
    ("encoder", "Енкодер лівого колеса",      "left_encoder", "ENC-1024-AB",   None, 10000, 820),
    ("encoder", "Енкодер правого колеса",     "right_encoder","ENC-1024-AB",   None, 10000, 820),
    ("imu",     "IMU MPU-9250",               "center_imu",   "IMU-MPU9250",   None, 20000, 820),
    ("lidar",   "LiDAR 360°",                 "front_lidar",  "LID-RPLA2",     None, 15000, 820),
    ("wheel",   "Колесо ліве d=120мм",        "left_wheel_hub","WHL-RUBBER-120", None, 8000, 820),
    ("wheel",   "Колесо праве d=120мм",       "right_wheel_hub","WHL-RUBBER-120", None, 8000, 820),
    ("controller","Бортовий контролер",       "main_ctrl",    "CTRL-RPI4",     None, 30000, 820),
]

ALERT_RULES = [
    ("Висока температура правого двигуна", "right_motor_temp", ">", 70.0, "warning",
     "Температура правого двигуна перевищила поріг 70°C."),
    ("Критична температура лівого двигуна", "left_motor_temp", ">", 85.0, "critical",
     "Перегрів лівого двигуна — аварійна зупинка."),
    ("Низький заряд батареї", "battery_soc", "<", 20.0, "warning",
     "SoC нижче 20% — направити робота на зарядку."),
    ("Деградація батареї (SoH)", "battery_soh", "<", 80.0, "warning",
     "Стан здоров'я батареї нижче 80% — планова заміна."),
    ("Висока вібрація правого двигуна", "right_motor_vib", ">", 0.6, "warning",
     "Вібрація правого двигуна > 0.6g — ймовірний знос підшипника."),
    ("Перегрів батареї", "battery_temp", ">", 50.0, "critical",
     "Температура батареї вище 50°C — негайна діагностика."),
]


USERS_SEED = [
    ("admin@progress.ua",    "admin123",    "Коваленко Олексій Петрович", "admin",
     "Системний адміністратор", "ІТ-відділ"),
    ("engineer@progress.ua", "engineer123", "Шевченко Марія Іванівна",    "engineer",
     "Інженер з надійності", "Відділ ТО"),
    ("operator@progress.ua", "operator123", "Литвиненко Олег Миколайович","operator",
     "Диспетчер цеху",        "Виробництво"),
]


async def seed_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:

        factory = (await db.execute(select(Factory).where(Factory.code == "PLANT-01"))).scalar_one_or_none()
        if not factory:
            factory = Factory(id=uuid.uuid4(), name="Завод \"Прогрес\"", code="PLANT-01", city="Київ")
            db.add(factory); await db.flush()

        line = (await db.execute(select(ProductionLine).where(ProductionLine.code == "LINE-01"))).scalar_one_or_none()
        if not line:
            line = ProductionLine(id=uuid.uuid4(), factory_id=factory.id,
                                  name="Лінія збирання №1", code="LINE-01",
                                  description="Основна лінія збирання електронних модулів")
            db.add(line); await db.flush()

        zones_existing = {z.name for z in (await db.execute(
            select(WorkshopZone).where(WorkshopZone.line_id == line.id))).scalars()}
        charging_zone_id = None
        for name, ztype, color, x0, y0, x1, y1 in ZONES:
            if name in zones_existing:
                continue
            z = WorkshopZone(line_id=line.id, name=name, zone_type=ztype, color_hex=color,
                             x_min=x0, y_min=y0, x_max=x1, y_max=y1)
            db.add(z)
            await db.flush()
            if ztype == "charging_area":
                charging_zone_id = z.id

        await db.flush()
        if not charging_zone_id:
            charging_zone_id = (await db.execute(
                select(WorkshopZone).where(WorkshopZone.line_id == line.id,
                                            WorkshopZone.zone_type == "charging_area"))).scalar_one().id

        existing_chargers = {c.code for c in (await db.execute(select(ChargingStation))).scalars()}
        for code, x, y in CHARGERS:
            if code not in existing_chargers:
                db.add(ChargingStation(zone_id=charging_zone_id, code=code,
                                       x_position=x, y_position=y, max_power_w=500))


        for email, pw, full, role, title, dept in USERS_SEED:
            existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if not existing:
                db.add(User(email=email, password_hash=hash_password(pw),
                            full_name=full, role=role, position_title=title, department=dept))


        for code, sn, model, client_id, status, x, y in ROBOTS_SEED:
            existing = (await db.execute(select(Robot).where(Robot.code == code))).scalar_one_or_none()
            if existing:
                continue
            rb = Robot(line_id=line.id, code=code, serial_number=sn, model=model,
                       mqtt_client_id=client_id, status=status,
                       last_x=x, last_y=y, firmware_version="v2.4.1")
            db.add(rb)
            await db.flush()
            for cat, name, pos, pn, soh, life, hours in COMPONENTS_PER_ROBOT:
                db.add(RobotComponent(robot_id=rb.id, category=cat, name=name,
                                      position_label=pos, part_number=pn,
                                      current_soh_pct=soh, expected_life_hours=life,
                                      current_hours=hours))


        existing_rules = {r.name for r in (await db.execute(select(AlertRule))).scalars()}
        for name, param, op, thr, sev, desc in ALERT_RULES:
            if name not in existing_rules:
                db.add(AlertRule(name=name, parameter=param, operator=op,
                                 threshold=thr, severity=sev, description=desc))


        if "Аномальна вібрація (адаптивний)" not in existing_rules:
            db.add(AlertRule(
                name="Аномальна вібрація (адаптивний)",
                parameter="right_motor_vib",
                operator=">",
                threshold=0.0,
                severity="warning",
                description=("Адаптивний поріг μ+3σ за 60 хв історії: "
                             "ловить статистичний outlier, який може ще "
                             "не перетнути абсолютний поріг."),
                mode="adaptive", window_minutes=60, k_sigma=3.0,
            ))

        await db.flush()


        any_ticket = (await db.execute(select(Ticket))).first()
        if not any_ticket:
            amr02 = (await db.execute(select(Robot).where(Robot.code == "AMR-02"))).scalar_one()
            right_motor = (await db.execute(
                select(RobotComponent).where(RobotComponent.robot_id == amr02.id,
                                             RobotComponent.position_label == "right_wheel")
            )).scalars().first()
            engineer = (await db.execute(
                select(User).where(User.email == "engineer@progress.ua")
            )).scalar_one()
            operator = (await db.execute(
                select(User).where(User.email == "operator@progress.ua")
            )).scalar_one()
            db.add(Ticket(
                robot_id=amr02.id,
                component_id=right_motor.id if right_motor else None,
                title="Перевірка правого двигуна AMR-02: підвищена вібрація",
                description="Телеметрія фіксує стійке зростання вібрації правого тягового "
                            "двигуна (~0.35g). Рекомендовано провести діагностику підшипника.",
                maintenance_type="predictive", priority="high", status="assigned",
                created_by=operator.id, assigned_to=engineer.id, estimated_hours=2.0,
            ))


        any_mission = (await db.execute(select(Mission))).first()
        if not any_mission:
            zones = list((await db.execute(
                select(WorkshopZone).where(WorkshopZone.line_id == line.id)
            )).scalars())
            warehouse_raw = next((z for z in zones if z.zone_type == "warehouse"
                                  and "сировин" in z.name.lower()), zones[0])
            assembly_a = next((z for z in zones if z.zone_type == "assembly"), zones[0])
            packaging = next((z for z in zones if z.zone_type == "packaging"), zones[0])
            fin_warehouse = next((z for z in zones if z.zone_type == "warehouse"
                                  and "готов" in z.name.lower()), zones[-1])

            amr01 = (await db.execute(select(Robot).where(Robot.code == "AMR-01"))).scalar_one()
            amr02 = (await db.execute(select(Robot).where(Robot.code == "AMR-02"))).scalar_one()
            operator = (await db.execute(
                select(User).where(User.email == "operator@progress.ua")
            )).scalar_one()

            db.add_all([
                Mission(robot_id=amr01.id, origin_zone_id=warehouse_raw.id,
                        destination_zone_id=assembly_a.id,
                        payload_type="raw_material", payload_weight_kg=18.0,
                        priority="medium", status="in_transit",
                        notes="Доставка плат на дільницю А",
                        created_by=operator.id,
                        started_at=datetime.now(timezone.utc)),
                Mission(robot_id=amr02.id, origin_zone_id=assembly_a.id,
                        destination_zone_id=packaging.id,
                        payload_type="semi_product", payload_weight_kg=22.5,
                        priority="high", status="assigned",
                        notes="Зібраний модуль до пакування",
                        created_by=operator.id),
                Mission(origin_zone_id=packaging.id,
                        destination_zone_id=fin_warehouse.id,
                        payload_type="finished_product", payload_weight_kg=15.0,
                        priority="low", status="queued",
                        notes="Поточний планований трансфер на склад",
                        created_by=operator.id),
            ])

        await db.commit()
        print("[seed] done — login with admin@progress.ua / admin123")


if __name__ == "__main__":
    asyncio.run(seed_all())
