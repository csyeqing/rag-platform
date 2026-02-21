from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.db.models import Base, RoleEnum, User
from app.db.session import engine
from app.services.retrieval_profile_service import ensure_default_profiles


def init_db() -> None:
    with Session(engine) as session:
        session.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        session.commit()
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        _ensure_schema_compat(session)
        _ensure_default_admin(session)
        ensure_default_profiles(session)


def _ensure_default_admin(db: Session) -> None:
    settings = get_settings()
    existing = db.query(User).filter(User.username == settings.default_admin_username).first()
    if existing:
        return
    admin = User(
        username=settings.default_admin_username,
        password_hash=get_password_hash(settings.default_admin_password),
        role=RoleEnum.admin,
        is_active=True,
    )
    db.add(admin)
    db.commit()


def _ensure_schema_compat(db: Session) -> None:
    # 为旧版本数据库补齐新增列，避免 create_all 无法升级现有表结构的问题。
    db.execute(text('ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS retrieval_profile_id UUID'))
    db.execute(text('CREATE INDEX IF NOT EXISTS ix_chat_sessions_retrieval_profile_id ON chat_sessions (retrieval_profile_id)'))
    db.execute(text("ALTER TABLE knowledge_libraries ADD COLUMN IF NOT EXISTS library_type VARCHAR(50) NOT NULL DEFAULT 'general'"))
    db.execute(text('CREATE INDEX IF NOT EXISTS ix_knowledge_libraries_library_type ON knowledge_libraries (library_type)'))
    db.execute(
        text('ALTER TABLE provider_configs ADD COLUMN IF NOT EXISTS context_window_tokens INTEGER NOT NULL DEFAULT 131072')
    )
    db.commit()
