from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.provider import ModelValidateRequest, ModelValidateResponse
from app.services.providers.base import ProviderConfigDTO
from app.services.providers.registry import provider_registry

router = APIRouter(prefix='/models', tags=['models'])


@router.post('/validate', response_model=ModelValidateResponse)
def validate_model(
    payload: ModelValidateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ModelValidateResponse:
    del db, current_user
    try:
        adapter = provider_registry.get(payload.provider_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    result = adapter.validate_credentials(
        ProviderConfigDTO(
            provider_type=payload.provider_type,
            endpoint_url=payload.endpoint_url,
            model_name=payload.model_name,
            api_key=payload.api_key,
        )
    )
    return ModelValidateResponse(valid=result.valid, message=result.message, capabilities=result.capabilities)
