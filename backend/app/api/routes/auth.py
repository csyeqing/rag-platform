from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, LoginResponse, TokenResponse
from app.utils.audit import write_audit_log

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/login', response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')

    token = create_access_token(str(user.id))

    write_audit_log(
        db,
        action='auth.login',
        resource_type='user',
        resource_id=str(user.id),
        user_id=user.id,
        metadata={'username': user.username},
    )

    return LoginResponse(
        token=TokenResponse(access_token=token),
        role=user.role.value,
        username=user.username,
    )
