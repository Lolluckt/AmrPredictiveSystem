"""Common FastAPI dependencies: auth guard + role/permission enforcement."""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models.user import User
from .roles import Permission, Role, has_permission
from .security import decode_token

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def current_user(
    token: str = Depends(oauth2),
    db: AsyncSession = Depends(get_session),
) -> User:
    claims = decode_token(token)
    if not claims or claims.get("typ") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access token",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        user_id = UUID(claims["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token subject")

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or gone")
    return user


def require_roles(*allowed: Role):
    """Dependency factory: ensure the current user has *any* of the given roles."""
    allowed_set = {r.value if isinstance(r, Role) else r for r in allowed}

    async def _dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed_set:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"Role '{user.role}' is not allowed here")
        return user

    return _dep


def require_permission(permission: Permission):
    """Dependency factory: check fine-grained RBAC permission."""

    async def _dep(user: User = Depends(current_user)) -> User:
        try:
            role = Role(user.role)
        except ValueError:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Unknown role '{user.role}'")
        if not has_permission(role, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"Missing permission '{permission.value}'")
        return user

    return _dep
