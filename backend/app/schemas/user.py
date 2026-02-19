from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserMeResponse(BaseModel):
    id: UUID
    username: str
    role: str
    is_active: bool
    created_at: datetime


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6, max_length=200)
    role: str = Field(default='user')


class UserUpdateRequest(BaseModel):
    password: str | None = Field(default=None, min_length=6, max_length=200)
    role: str | None = None
    is_active: bool | None = None


class UserListItemResponse(BaseModel):
    id: UUID
    username: str
    role: str
    is_active: bool
    created_at: datetime
