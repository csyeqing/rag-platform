from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=settings.jwt_expire_minutes)
    )
    payload = {'sub': subject, 'exp': expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        subject = payload.get('sub')
        if not subject:
            raise JWTError('Missing subject')
        return str(subject)
    except JWTError as exc:
        raise ValueError('Invalid token') from exc


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet:
    settings = get_settings()
    key_value = settings.encryption_key or settings.secret_key
    try:
        key_bytes = key_value.encode('utf-8')
        if len(key_bytes) == 44:
            return Fernet(key_bytes)
    except Exception:
        pass
    return Fernet(_derive_fernet_key(key_value))


def encrypt_secret(value: str) -> str:
    if not value:
        return ''
    return get_fernet().encrypt(value.encode('utf-8')).decode('utf-8')


def decrypt_secret(value: str) -> str:
    if not value:
        return ''
    return get_fernet().decrypt(value.encode('utf-8')).decode('utf-8')


def mask_secret(value: str, left: int = 3, right: int = 3) -> str:
    if len(value) <= left + right:
        return '*' * len(value)
    return f"{value[:left]}{'*' * (len(value) - left - right)}{value[-right:]}"
