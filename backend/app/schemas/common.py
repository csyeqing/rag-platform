from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class APIMessage(BaseModel):
    message: str


class Pagination(BaseModel):
    total: int


class UUIDModel(BaseModel):
    id: UUID


class TimestampModel(BaseModel):
    created_at: datetime
    updated_at: datetime | None = None
