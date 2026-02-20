from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.models import RetrievalProfile, RoleEnum, User
from app.db.session import get_db
from app.schemas.settings import (
    RetrievalProfileCreateRequest,
    RetrievalProfileResponse,
    RetrievalProfileUpdateRequest,
)
from app.services.retrieval_profile_service import (
    create_profile,
    delete_profile,
    get_profile_or_404,
    list_profiles,
    update_profile,
)
from app.utils.audit import write_audit_log

router = APIRouter(prefix='/settings', tags=['settings'])


@router.get('/retrieval-profiles', response_model=list[RetrievalProfileResponse])
def list_retrieval_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RetrievalProfileResponse]:
    del current_user
    rows = list_profiles(db, include_inactive=False)
    return [_to_profile_response(item) for item in rows]


@router.post('/retrieval-profiles', response_model=RetrievalProfileResponse)
def create_retrieval_profile(
    payload: RetrievalProfileCreateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_role(RoleEnum.admin)),
) -> RetrievalProfileResponse:
    created = create_profile(
        db,
        current_user=current_admin,
        profile_key=payload.profile_key,
        name=payload.name,
        profile_type=payload.profile_type,
        description=payload.description,
        config=payload.config.model_dump(),
        is_default=payload.is_default,
        is_builtin=payload.is_builtin,
        is_active=payload.is_active,
    )
    write_audit_log(
        db,
        action='settings.retrieval_profile.create',
        resource_type='retrieval_profile',
        resource_id=str(created.id),
        user_id=current_admin.id,
        metadata={'profile_key': created.profile_key, 'profile_type': created.profile_type.value},
    )
    return _to_profile_response(created)


@router.put('/retrieval-profiles/{profile_id}', response_model=RetrievalProfileResponse)
def update_retrieval_profile(
    profile_id: UUID,
    payload: RetrievalProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_role(RoleEnum.admin)),
) -> RetrievalProfileResponse:
    profile = get_profile_or_404(db, profile_id)
    updated = update_profile(
        db,
        profile=profile,
        profile_key=payload.profile_key,
        name=payload.name,
        profile_type=payload.profile_type,
        description=payload.description,
        config=(payload.config.model_dump() if payload.config is not None else None),
        is_default=payload.is_default,
        is_active=payload.is_active,
    )
    write_audit_log(
        db,
        action='settings.retrieval_profile.update',
        resource_type='retrieval_profile',
        resource_id=str(updated.id),
        user_id=current_admin.id,
        metadata={'profile_key': updated.profile_key, 'profile_type': updated.profile_type.value},
    )
    return _to_profile_response(updated)


@router.delete('/retrieval-profiles/{profile_id}')
def delete_retrieval_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_role(RoleEnum.admin)),
) -> None:
    profile = get_profile_or_404(db, profile_id)
    delete_profile(db, profile)
    write_audit_log(
        db,
        action='settings.retrieval_profile.delete',
        resource_type='retrieval_profile',
        resource_id=str(profile_id),
        user_id=current_admin.id,
        metadata={'profile_key': profile.profile_key},
    )


def _to_profile_response(item: RetrievalProfile) -> RetrievalProfileResponse:
    config = item.config_json or {}
    return RetrievalProfileResponse(
        id=item.id,
        profile_key=item.profile_key,
        name=item.name,
        profile_type=item.profile_type.value,
        description=item.description,
        config=config,
        is_default=item.is_default,
        is_builtin=item.is_builtin,
        is_active=item.is_active,
        created_by=item.created_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
