"""SQLAlchemy model registry.

Re-exporting every model here guarantees that Base.metadata is fully populated
before Alembic autogenerate scans it or the seed script creates all tables.
"""
from .user import User, RefreshToken
from .factory import Factory, ProductionLine, WorkshopZone, ChargingStation
from .robot import Robot, RobotComponent
from .telemetry import TelemetrySnapshot
from .alert import AlertRule, AnomalyEvent
from .ticket import Ticket, TicketComment
from .mission import Mission
from .audit import AuditLog
