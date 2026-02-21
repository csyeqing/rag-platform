from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RetrievalProfileConfig(BaseModel):
    rag_min_top1_score: float = Field(default=0.30, ge=0.0, le=1.5)
    rag_min_support_score: float = Field(default=0.18, ge=0.0, le=1.5)
    rag_min_support_count: int = Field(default=2, ge=1, le=8)
    rag_min_item_score: float = Field(default=0.10, ge=0.0, le=1.5)
    rag_graph_max_terms: int = Field(default=12, ge=4, le=40)
    graph_channel_weight: float = Field(default=0.65, ge=0.1, le=1.2)
    graph_only_penalty: float = Field(default=0.55, ge=0.1, le=1.0)
    vector_semantic_min: float = Field(default=0.12, ge=0.0, le=1.0)
    alias_intent_enabled: bool = True
    alias_mining_max_terms: int = Field(default=8, ge=0, le=24)
    co_reference_enabled: bool = True
    vector_candidate_multiplier: int = Field(default=3, ge=2, le=20)
    keyword_candidate_multiplier: int = Field(default=3, ge=2, le=20)
    graph_candidate_multiplier: int = Field(default=4, ge=2, le=24)
    fallback_relax_enabled: bool = True
    fallback_top1_relax: float = Field(default=0.08, ge=0.0, le=0.30)
    fallback_support_relax: float = Field(default=0.06, ge=0.0, le=0.30)
    fallback_item_relax: float = Field(default=0.04, ge=0.0, le=0.20)
    summary_intent_enabled: bool = True
    summary_expand_factor: int = Field(default=3, ge=1, le=8)
    summary_min_chunks: int = Field(default=8, ge=4, le=24)
    summary_per_file_cap: int = Field(default=2, ge=1, le=6)
    summary_min_files: int = Field(default=3, ge=1, le=10)
    keyword_fallback_expand_on_weak_hits: bool = True
    keyword_fallback_max_chunks: int = Field(default=240, ge=20, le=800)
    keyword_fallback_min_score: float = Field(default=0.08, ge=0.0, le=1.5)
    keyword_fallback_scan_limit: int = Field(default=8000, ge=200, le=20000)


class RetrievalProfileBaseRequest(BaseModel):
    profile_key: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=120)
    profile_type: str = Field(default='general')
    description: str | None = None
    config: RetrievalProfileConfig
    is_default: bool = False
    is_active: bool = True


class RetrievalProfileCreateRequest(RetrievalProfileBaseRequest):
    is_builtin: bool = False


class RetrievalProfileUpdateRequest(BaseModel):
    profile_key: str | None = Field(default=None, min_length=2, max_length=80)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    profile_type: str | None = None
    description: str | None = None
    config: RetrievalProfileConfig | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class RetrievalProfileResponse(BaseModel):
    id: UUID
    profile_key: str
    name: str
    profile_type: str
    description: str | None
    config: RetrievalProfileConfig
    is_default: bool
    is_builtin: bool
    is_active: bool
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
