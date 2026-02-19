from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeLibraryCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None
    owner_type: str = 'private'
    tags: list[str] = Field(default_factory=list)
    root_path: str | None = None


class KnowledgeLibraryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    owner_type: str | None = None
    tags: list[str] | None = None


class KnowledgeLibraryResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    owner_type: str
    owner_id: UUID | None
    tags: list[str]
    root_path: str
    created_at: datetime
    updated_at: datetime


class SyncDirectoryRequest(BaseModel):
    library_id: UUID
    directory_path: str
    recursive: bool = True


class RebuildIndexRequest(BaseModel):
    library_id: UUID


class IngestionTaskResponse(BaseModel):
    id: UUID
    task_type: str
    status: str
    library_id: UUID
    detail: dict
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class KnowledgeFileResponse(BaseModel):
    id: UUID
    library_id: UUID
    filename: str
    filepath: str
    file_type: str
    status: str
    created_at: datetime
    updated_at: datetime


class KnowledgeGraphNodeResponse(BaseModel):
    id: UUID
    name: str
    display_name: str
    entity_type: str
    frequency: int


class KnowledgeGraphEdgeResponse(BaseModel):
    id: UUID
    source_entity_id: UUID
    source_entity: str
    target_entity_id: UUID
    target_entity: str
    relation_type: str
    weight: int


class KnowledgeGraphResponse(BaseModel):
    library_id: UUID
    node_count: int
    edge_count: int
    nodes: list[KnowledgeGraphNodeResponse]
    edges: list[KnowledgeGraphEdgeResponse]


class KnowledgeGraphRebuildResponse(BaseModel):
    library_id: UUID
    node_count: int
    edge_count: int
    chunk_count: int
    message: str
