from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.security import get_password_hash
from app.db.models import RoleEnum, User
from app.db.session import get_db
from app.schemas.user import UserCreateRequest, UserListItemResponse, UserUpdateRequest
from app.utils.audit import write_audit_log

router = APIRouter(prefix='/admin/users', tags=['admin-users'])


@router.get('', response_model=list[UserListItemResponse])
def list_users(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_role(RoleEnum.admin)),
) -> list[UserListItemResponse]:
    del current_admin
    rows = db.query(User).order_by(User.created_at.desc()).all()
    return [
        UserListItemResponse(
            id=item.id,
            username=item.username,
            role=item.role.value,
            is_active=item.is_active,
            created_at=item.created_at,
        )
        for item in rows
    ]


@router.post('', response_model=UserListItemResponse)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_role(RoleEnum.admin)),
) -> UserListItemResponse:
    exists = db.query(User).filter(User.username == payload.username).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Username already exists')

    try:
        role = RoleEnum(payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='role must be admin or user') from exc

    created = User(
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        role=role,
        is_active=True,
    )
    db.add(created)
    db.commit()
    db.refresh(created)

    write_audit_log(
        db,
        action='admin.user.create',
        resource_type='user',
        resource_id=str(created.id),
        user_id=current_admin.id,
        metadata={'username': created.username, 'role': created.role.value},
    )

    return UserListItemResponse(
        id=created.id,
        username=created.username,
        role=created.role.value,
        is_active=created.is_active,
        created_at=created.created_at,
    )


@router.put('/{user_id}', response_model=UserListItemResponse)
def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_role(RoleEnum.admin)),
) -> UserListItemResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    if payload.role is not None:
        try:
            new_role = RoleEnum(payload.role)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='role must be admin or user') from exc
        if user.id == current_admin.id and new_role != RoleEnum.admin:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Cannot downgrade current admin')
        user.role = new_role

    if payload.password is not None:
        user.password_hash = get_password_hash(payload.password)

    if payload.is_active is not None:
        if user.id == current_admin.id and payload.is_active is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Cannot deactivate current admin')
        user.is_active = payload.is_active

    db.add(user)
    db.commit()
    db.refresh(user)

    write_audit_log(
        db,
        action='admin.user.update',
        resource_type='user',
        resource_id=str(user.id),
        user_id=current_admin.id,
        metadata={'role': user.role.value, 'is_active': user.is_active},
    )

    return UserListItemResponse(
        id=user.id,
        username=user.username,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
    )
