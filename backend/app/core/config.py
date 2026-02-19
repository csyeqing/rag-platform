from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'RAG Web MVP'
    app_env: str = 'development'
    secret_key: str = '<SECRET>'
    jwt_algorithm: str = 'HS256'
    jwt_expire_minutes: int = 120
    database_url: str = 'postgresql+psycopg://rag:rag@localhost:5432/rag_mvp'
    encryption_key: str | None = None
    cors_origins: str | list[str] = Field(default='["http://localhost:5173"]')
    storage_root: str = './data'
    kb_sync_root: str = './data/knowledge'
    default_admin_username: str = 'admin'
    default_admin_password: str = 'admin123456'
    default_embedding_dim: int = 1536
    embedding_backend: str = 'local'
    embedding_provider_type: str = 'openai_compatible'
    embedding_endpoint_url: str = ''
    embedding_model_name: str = 'BAAI/bge-m3'
    embedding_api_key: str = ''
    embedding_local_device: str = 'auto'
    embedding_batch_size: int = 16
    embedding_fallback_hash: bool = True
    request_timeout_seconds: int = 30

    @property
    def parsed_cors_origins(self) -> list[str]:
        if isinstance(self.cors_origins, list):
            return self.cors_origins
        try:
            parsed: Any = json.loads(self.cors_origins)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
        return [item.strip() for item in str(self.cors_origins).split(',') if item.strip()]

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_root).resolve()

    @property
    def kb_sync_path(self) -> Path:
        return Path(self.kb_sync_root).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
