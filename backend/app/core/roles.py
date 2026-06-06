"""Role-based access control.

The system has exactly 3 roles, chosen to align with typical factory-floor
responsibilities without an explosion of privileges:

    admin    — full control; manages users, system config, and can override
               any maintenance/mission state.
    engineer — reliability engineer; owns tickets, predictive analytics,
               alert rules, firmware, and component replacement history.
    operator — shift-floor dispatcher; views dashboards, creates/cancels
               missions, acknowledges alerts, issues immediate commands.

Permission checks are expressed declaratively via ``ROLE_PERMISSIONS`` and
enforced by the ``require_roles`` / ``require_permission`` FastAPI deps.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet


class Role(str, Enum):
    ADMIN = "admin"
    ENGINEER = "engineer"
    OPERATOR = "operator"


class Permission(str, Enum):

    USERS_MANAGE = "users:manage"
    SYSTEM_CONFIG = "system:config"


    ROBOTS_VIEW = "robots:view"
    ROBOTS_EDIT = "robots:edit"
    ROBOTS_COMMAND = "robots:command"


    TELEMETRY_VIEW = "telemetry:view"
    PREDICTIVE_VIEW = "predictive:view"
    PREDICTIVE_CONFIGURE = "predictive:configure"


    ALERTS_VIEW = "alerts:view"
    ALERTS_ACK = "alerts:ack"
    ALERTS_MANAGE = "alerts:manage"


    TICKETS_VIEW = "tickets:view"
    TICKETS_EDIT = "tickets:edit"
    TICKETS_CREATE = "tickets:create"
    TICKETS_CLOSE = "tickets:close"


    MISSIONS_VIEW = "missions:view"
    MISSIONS_CREATE = "missions:create"
    MISSIONS_CANCEL = "missions:cancel"


ROLE_PERMISSIONS: Dict[Role, FrozenSet[Permission]] = {
    Role.OPERATOR: frozenset({
        Permission.ROBOTS_VIEW,
        Permission.ROBOTS_COMMAND,
        Permission.TELEMETRY_VIEW,
        Permission.ALERTS_VIEW, Permission.ALERTS_ACK,
        Permission.TICKETS_VIEW, Permission.TICKETS_CREATE,
        Permission.MISSIONS_VIEW, Permission.MISSIONS_CREATE, Permission.MISSIONS_CANCEL,
    }),
    Role.ENGINEER: frozenset({
        Permission.ROBOTS_VIEW, Permission.ROBOTS_EDIT, Permission.ROBOTS_COMMAND,
        Permission.TELEMETRY_VIEW,
        Permission.PREDICTIVE_VIEW, Permission.PREDICTIVE_CONFIGURE,
        Permission.ALERTS_VIEW, Permission.ALERTS_ACK, Permission.ALERTS_MANAGE,
        Permission.TICKETS_VIEW, Permission.TICKETS_EDIT,
        Permission.TICKETS_CREATE, Permission.TICKETS_CLOSE,
        Permission.MISSIONS_VIEW, Permission.MISSIONS_CREATE, Permission.MISSIONS_CANCEL,
    }),

    Role.ADMIN: frozenset(p for p in Permission),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
