from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import ProviderConfig, User
from app.db.session import get_db
from app.schemas.provider import ProviderCreateRequest, ProviderResponse, ProviderUpdateRequest
from app.services.provider_service import create_provider_config, serialize_provider, update_provider_config
from app.utils.audit import write_audit_log

router = APIRouter(prefix='/providers', tags=['providers'])


@router.post('', response_model=ProviderResponse)
def create_provider(
    payload: ProviderCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProviderResponse:
    config = create_provider_config(db, current_user, payload)
    write_audit_log(
        db,
        action='provider.create',
        resource_type='provider_config',
        resource_id=str(config.id),
        user_id=current_user.id,
        metadata={'provider_type': config.provider_type.value},
    )
    return ProviderResponse(**serialize_provider(config))


@router.get('', response_model=list[ProviderResponse])
def list_provider_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProviderResponse]:
    rows = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.owner_id == current_user.id)
        .order_by(ProviderConfig.updated_at.desc())
        .all()
    )
    return [ProviderResponse(**serialize_provider(item)) for item in rows]


@router.put('/{provider_id}', response_model=ProviderResponse)
def update_provider(
    provider_id: UUID,
    payload: ProviderUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProviderResponse:
    config = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.id == provider_id, ProviderConfig.owner_id == current_user.id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Provider config not found')

    config = update_provider_config(db, current_user, config, payload)
    write_audit_log(
        db,
        action='provider.update',
        resource_type='provider_config',
        resource_id=str(config.id),
        user_id=current_user.id,
    )
    return ProviderResponse(**serialize_provider(config))


@router.delete('/{provider_id}')
def delete_provider(
    provider_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    config = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.id == provider_id, ProviderConfig.owner_id == current_user.id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Provider config not found')

    db.delete(config)
    db.commit()

    write_audit_log(
        db,
        action='provider.delete',
        resource_type='provider_config',
        resource_id=str(provider_id),
        user_id=current_user.id,
    )
    return {'message': 'deleted'}
