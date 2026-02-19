from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class LoginResponse(BaseModel):
    token: TokenResponse
    role: str
    username: str
