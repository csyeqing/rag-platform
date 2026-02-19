from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def write_audit_log(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    user_id: UUID | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    record = AuditLog(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        metadata_json=metadata or {},
    )
    db.add(record)
    db.commit()
