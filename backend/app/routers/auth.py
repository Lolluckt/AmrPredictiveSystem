"""Auth endpoints: login (email+password), refresh, logout, me."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..core.deps import current_user
from ..core.security import (
    create_access_token, create_refresh_token, decode_token,
    hash_password, verify_password,
)
from ..db import get_session
from ..models.user import RefreshToken, User
from ..schemas.auth import LoginRequest, RefreshRequest, TokenPair
from ..schemas.user import UserOut
from ..services.audit import record as audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

settings = get_settings()


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _issue_tokens(db: AsyncSession, user: User) -> TokenPair:
    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id)
    expires = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    db.add(RefreshToken(user_id=user.id, token_hash=_token_hash(refresh), expires_at=expires))
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_session)) -> TokenPair:
    q = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = q.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Невірний email або пароль")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Акаунт деактивовано")
    pair = await _issue_tokens(db, user)

    try:
        await audit(db, user_id=user.id, action="auth.login",
                    entity_type="user", entity_id=user.id,
                    details={"email": user.email})
        await db.commit()
    except Exception:
        await db.rollback()
    return pair


@router.post("/login/form", response_model=TokenPair, include_in_schema=False)
async def login_form(form: OAuth2PasswordRequestForm = Depends(),
                     db: AsyncSession = Depends(get_session)) -> TokenPair:
    """Compatibility endpoint so the OpenAPI Authorize button works."""
    q = await db.execute(select(User).where(User.email == form.username.lower()))
    user = q.scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return await _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_session)) -> TokenPair:
    claims = decode_token(req.refresh_token)
    if not claims or claims.get("typ") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh-токен недійсний")

    q = await db.execute(select(RefreshToken).where(
        RefreshToken.token_hash == _token_hash(req.refresh_token),
        RefreshToken.is_revoked.is_(False),
    ))
    stored = q.scalar_one_or_none()
    if not stored or stored.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh-токен вичерпано")

    user = await db.get(User, stored.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Користувач недоступний")


    stored.is_revoked = True
    await db.flush()
    return await _issue_tokens(db, user)


@router.post("/logout")
async def logout(req: RefreshRequest, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    q = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == _token_hash(req.refresh_token)))
    stored = q.scalar_one_or_none()
    if stored:
        stored.is_revoked = True
        await db.commit()
    return {"detail": "logged_out"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> User:
    return user
