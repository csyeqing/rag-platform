from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.db.models import Base, RoleEnum, User
from app.db.session import engine


def init_db() -> None:
    with Session(engine) as session:
        session.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        session.commit()
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        _ensure_default_admin(session)


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
