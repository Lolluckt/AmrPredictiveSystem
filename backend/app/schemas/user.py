from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["admin", "engineer", "operator"]


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    role: Role = "operator"
    department: Optional[str] = None
    position_title: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=120)


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[Role] = None
    department: Optional[str] = None
    position_title: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=120)


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    last_login_at: Optional[datetime] = None
    created_at: datetime


class UserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: EmailStr
    full_name: str
    role: Role
    department: Optional[str]
    is_active: bool
