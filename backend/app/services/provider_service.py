from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.db.models import ProviderConfig, ProviderTypeEnum, User
from app.schemas.provider import ProviderCreateRequest, ProviderUpdateRequest


def create_provider_config(db: Session, user: User, request: ProviderCreateRequest) -> ProviderConfig:
    try:
        provider_type = ProviderTypeEnum(request.provider_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unsupported provider_type') from exc

    config = ProviderConfig(
        name=request.name,
        provider_type=provider_type,
        endpoint_url=request.endpoint_url,
        model_name=request.model_name,
        context_window_tokens=request.context_window_tokens,
        api_key_encrypted=encrypt_secret(request.api_key),
        is_default=request.is_default,
        capabilities=request.capabilities,
        owner_id=user.id,
    )
    if request.is_default:
        _clear_default_flag(db, user.id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def update_provider_config(db: Session, user: User, config: ProviderConfig, request: ProviderUpdateRequest) -> ProviderConfig:
    if request.name is not None:
        config.name = request.name
    if request.provider_type is not None:
        try:
            config.provider_type = ProviderTypeEnum(request.provider_type)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unsupported provider_type') from exc
    if request.endpoint_url is not None:
        config.endpoint_url = request.endpoint_url
    if request.model_name is not None:
        config.model_name = request.model_name
    if request.context_window_tokens is not None:
        config.context_window_tokens = request.context_window_tokens
    if request.capabilities is not None:
        config.capabilities = request.capabilities
    if request.api_key is not None:
        config.api_key_encrypted = encrypt_secret(request.api_key)
    if request.is_default is not None:
        if request.is_default:
            _clear_default_flag(db, user.id)
        config.is_default = request.is_default

    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def serialize_provider(config: ProviderConfig) -> dict:
    api_key_plain = decrypt_secret(config.api_key_encrypted)
    return {
        'id': config.id,
        'name': config.name,
        'provider_type': config.provider_type.value,
        'endpoint_url': config.endpoint_url,
        'model_name': config.model_name,
        'context_window_tokens': config.context_window_tokens,
        'is_default': config.is_default,
        'capabilities': config.capabilities,
        'owner_id': config.owner_id,
        'api_key_masked': mask_secret(api_key_plain),
        'created_at': config.created_at,
        'updated_at': config.updated_at,
    }


def to_runtime_config(config: ProviderConfig) -> dict:
    return {
        'provider_type': config.provider_type.value,
        'endpoint_url': config.endpoint_url,
        'model_name': config.model_name,
        'api_key': decrypt_secret(config.api_key_encrypted),
        'context_window_tokens': config.context_window_tokens,
    }


def _clear_default_flag(db: Session, owner_id) -> None:
    db.query(ProviderConfig).filter(ProviderConfig.owner_id == owner_id).update({'is_default': False})
    db.flush()
