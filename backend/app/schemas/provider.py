from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProviderBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    provider_type: str
    endpoint_url: str
    model_name: str
    is_default: bool = False
    capabilities: dict = Field(default_factory=dict)


class ProviderCreateRequest(ProviderBase):
    api_key: str = Field(min_length=1)


class ProviderUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    provider_type: str | None = None
    endpoint_url: str | None = None
    model_name: str | None = None
    is_default: bool | None = None
    capabilities: dict | None = None
    api_key: str | None = None


class ProviderResponse(ProviderBase):
    id: UUID
    owner_id: UUID
    api_key_masked: str
    created_at: datetime
    updated_at: datetime


class ModelValidateRequest(BaseModel):
    provider_type: str
    endpoint_url: str
    model_name: str
    api_key: str


class ModelValidateResponse(BaseModel):
    valid: bool
    message: str
    capabilities: dict = Field(default_factory=dict)
