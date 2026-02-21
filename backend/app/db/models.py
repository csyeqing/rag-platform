from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RoleEnum(str, enum.Enum):
    admin = 'admin'
    user = 'user'


class ProviderTypeEnum(str, enum.Enum):
    openai = 'openai'
    anthropic = 'anthropic'
    gemini = 'gemini'
    openai_compatible = 'openai_compatible'


class OwnerTypeEnum(str, enum.Enum):
    private = 'private'
    shared = 'shared'


class KnowledgeLibraryTypeEnum(str, enum.Enum):
    general = 'general'
    novel_story = 'novel_story'
    enterprise_docs = 'enterprise_docs'
    scientific_paper = 'scientific_paper'
    humanities_paper = 'humanities_paper'


class IngestionTaskTypeEnum(str, enum.Enum):
    sync_directory = 'sync_directory'
    upload = 'upload'
    rebuild_index = 'rebuild_index'


class IngestionTaskStatusEnum(str, enum.Enum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'


class ChatRoleEnum(str, enum.Enum):
    system = 'system'
    user = 'user'
    assistant = 'assistant'


class RetrievalProfileTypeEnum(str, enum.Enum):
    general = 'general'
    novel_story = 'novel_story'
    enterprise_docs = 'enterprise_docs'
    scientific_paper = 'scientific_paper'
    humanities_paper = 'humanities_paper'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), default=RoleEnum.user)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    provider_configs: Mapped[list['ProviderConfig']] = relationship(back_populates='owner')
    chat_sessions: Mapped[list['ChatSession']] = relationship(back_populates='user')


class ProviderConfig(Base):
    __tablename__ = 'provider_configs'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    provider_type: Mapped[ProviderTypeEnum] = mapped_column(Enum(ProviderTypeEnum), index=True)
    endpoint_url: Mapped[str] = mapped_column(String(500))
    model_name: Mapped[str] = mapped_column(String(200))
    context_window_tokens: Mapped[int] = mapped_column(Integer, default=131072)
    api_key_encrypted: Mapped[str] = mapped_column(Text)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[User] = relationship(back_populates='provider_configs')


class KnowledgeLibrary(Base):
    __tablename__ = 'knowledge_libraries'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    library_type: Mapped[str] = mapped_column(String(50), default=KnowledgeLibraryTypeEnum.general.value, index=True)
    owner_type: Mapped[OwnerTypeEnum] = mapped_column(Enum(OwnerTypeEnum), default=OwnerTypeEnum.private)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    root_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    files: Mapped[list['KnowledgeFile']] = relationship(back_populates='library', cascade='all, delete-orphan')


class KnowledgeFile(Base):
    __tablename__ = 'knowledge_files'
    __table_args__ = (UniqueConstraint('library_id', 'filepath', name='uq_library_filepath'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    library_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('knowledge_libraries.id', ondelete='CASCADE')
    )
    filename: Mapped[str] = mapped_column(String(255), index=True)
    filepath: Mapped[str] = mapped_column(String(700))
    file_type: Mapped[str] = mapped_column(String(30), default='txt')
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default='indexed')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    library: Mapped[KnowledgeLibrary] = relationship(back_populates='files')
    chunks: Mapped[list['Chunk']] = relationship(back_populates='file', cascade='all, delete-orphan')


class Chunk(Base):
    __tablename__ = 'chunks'
    __table_args__ = (
        Index('ix_chunks_library_id', 'library_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    library_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('knowledge_libraries.id', ondelete='CASCADE')
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('knowledge_files.id', ondelete='CASCADE')
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    file: Mapped[KnowledgeFile] = relationship(back_populates='chunks')


class KnowledgeEntity(Base):
    __tablename__ = 'knowledge_entities'
    __table_args__ = (
        UniqueConstraint('library_id', 'name', name='uq_kg_entity_library_name'),
        Index('ix_kg_entities_library_frequency', 'library_id', 'frequency'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    library_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('knowledge_libraries.id', ondelete='CASCADE')
    )
    name: Mapped[str] = mapped_column(String(160), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str] = mapped_column(String(50), default='concept')
    frequency: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeRelation(Base):
    __tablename__ = 'knowledge_relations'
    __table_args__ = (
        UniqueConstraint(
            'library_id',
            'source_entity_id',
            'target_entity_id',
            'relation_type',
            name='uq_kg_relation_unique',
        ),
        Index('ix_kg_relations_library_weight', 'library_id', 'weight'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    library_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('knowledge_libraries.id', ondelete='CASCADE')
    )
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('knowledge_entities.id', ondelete='CASCADE')
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('knowledge_entities.id', ondelete='CASCADE')
    )
    relation_type: Mapped[str] = mapped_column(String(60), default='co_occurs')
    weight: Mapped[int] = mapped_column(Integer, default=1)
    evidence_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatSession(Base):
    __tablename__ = 'chat_sessions'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    title: Mapped[str] = mapped_column(String(200), default='新会话')
    provider_config_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    library_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    retrieval_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    show_citations: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates='chat_sessions')
    messages: Mapped[list['ChatMessage']] = relationship(back_populates='session', cascade='all, delete-orphan')


class ChatMessage(Base):
    __tablename__ = 'chat_messages'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('chat_sessions.id', ondelete='CASCADE')
    )
    role: Mapped[ChatRoleEnum] = mapped_column(Enum(ChatRoleEnum))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ChatSession] = relationship(back_populates='messages')


class IngestionTask(Base):
    __tablename__ = 'ingestion_tasks'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_type: Mapped[IngestionTaskTypeEnum] = mapped_column(Enum(IngestionTaskTypeEnum))
    status: Mapped[IngestionTaskStatusEnum] = mapped_column(
        Enum(IngestionTaskStatusEnum), default=IngestionTaskStatusEnum.queued
    )
    library_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('knowledge_libraries.id'))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(120), index=True)
    resource_id: Mapped[str] = mapped_column(String(120), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RetrievalProfile(Base):
    __tablename__ = 'retrieval_profiles'
    __table_args__ = (
        UniqueConstraint('profile_key', name='uq_retrieval_profiles_key'),
        Index('ix_retrieval_profiles_is_default', 'is_default'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_key: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(120))
    profile_type: Mapped[RetrievalProfileTypeEnum] = mapped_column(
        Enum(RetrievalProfileTypeEnum),
        default=RetrievalProfileTypeEnum.general,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
