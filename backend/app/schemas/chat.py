from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatSessionCreateRequest(BaseModel):
    title: str = Field(default='新会话', min_length=1, max_length=200)
    provider_config_id: UUID | None = None
    library_id: UUID | None = None
    retrieval_profile_id: UUID | None = None
    show_citations: bool = True


class ChatSessionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    provider_config_id: UUID | None = None
    library_id: UUID | None = None
    retrieval_profile_id: UUID | None = None
    show_citations: bool | None = None


class ChatSessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    provider_config_id: UUID | None
    library_id: UUID | None
    retrieval_profile_id: UUID | None
    show_citations: bool
    created_at: datetime
    updated_at: datetime


class ChatMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    stream: bool = True
    provider_config_id: UUID | None = None
    library_ids: list[UUID] | None = None
    retrieval_profile_id: UUID | None = None
    top_k: int = 5
    use_rerank: bool = False
    show_citations: bool = True
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 1024


class Citation(BaseModel):
    library_id: UUID
    file_id: UUID
    file_name: str
    chunk_id: UUID
    score: float
    snippet: str


class ChatMessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    citations: list[dict]
    created_at: datetime


class ChatMessageListResponse(BaseModel):
    items: list[ChatMessageResponse]
