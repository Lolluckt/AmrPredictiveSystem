"""User management — admin-only."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deps import require_roles
from ..core.roles import Role
from ..core.security import hash_password
from ..db import get_session
from ..models.user import User
from ..schemas.user import UserCreate, UserListItem, UserOut, UserUpdate
from ..services.audit import record as audit
from ..services.event_bus import bus

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserListItem])
async def list_users(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles(Role.ADMIN)),
) -> list[User]:
    res = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(res.scalars())


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_roles(Role.ADMIN)),
) -> User:
    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        department=payload.department,
        position_title=payload.position_title,
        is_active=payload.is_active,
    )
    db.add(user)
    try:
        await audit(db, user_id=admin.id, action="user.create",
                    entity_type="user", entity_id=user.id,
                    details={"email": payload.email, "role": payload.role})
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email вже використовується")
    await db.refresh(user)
    bus.publish("user", "create", entity_id=user.id,
                data={"id": str(user.id), "email": user.email, "role": user.role})
    return user


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles(Role.ADMIN)),
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Користувача не знайдено")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_roles(Role.ADMIN)),
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Користувача не знайдено")
    data = payload.model_dump(exclude_none=True)
    if "password" in data:
        user.password_hash = hash_password(data.pop("password"))
        data["password_changed"] = True
    for k, v in data.items():
        if k == "password_changed":
            continue
        setattr(user, k, v)
    await audit(db, user_id=admin.id, action="user.update",
                entity_type="user", entity_id=user.id, details=data)
    await db.commit()
    await db.refresh(user)
    bus.publish("user", "update", entity_id=user.id,
                data={"id": str(user.id), "email": user.email, "role": user.role,
                      "is_active": user.is_active})
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_roles(Role.ADMIN)),
):
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неможливо видалити себе")
    user = await db.get(User, user_id)
    if not user:
        return
    await audit(db, user_id=admin.id, action="user.delete",
                entity_type="user", entity_id=user.id,
                details={"email": user.email})
    await db.delete(user)
    await db.commit()
    bus.publish("user", "delete", entity_id=user_id, data={"id": str(user_id)})
