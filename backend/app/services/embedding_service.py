from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.providers.base import EmbeddingRequest, ProviderConfigDTO
from app.services.providers.local_algorithms import hash_embedding
from app.services.providers.registry import provider_registry

logger = logging.getLogger('app.request')
_local_model_lock = threading.Lock()
_local_model: Any | None = None
_local_model_key: str | None = None

# 配置模型缓存目录（持久化，避免每次重启都重新下载）
_MODEL_CACHE_DIR = Path(__file__).parent.parent.parent / '.cache' / 'models'
_MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ['HF_HOME'] = str(_MODEL_CACHE_DIR / 'huggingface')
os.environ['TRANSFORMERS_CACHE'] = str(_MODEL_CACHE_DIR / 'transformers')


def normalize_vector_dim(vector: list[float], target_dim: int) -> list[float]:
    current_dim = len(vector)
    if current_dim == target_dim:
        return vector
    if current_dim > target_dim:
        return vector[:target_dim]
    return vector + [0.0] * (target_dim - current_dim)


def _hash_embed_texts(texts: list[str], target_dim: int) -> list[list[float]]:
    return [normalize_vector_dim(hash_embedding(text, dim=target_dim), target_dim) for text in texts]


def _embed_with_remote_provider(texts: list[str], *, target_dim: int, batch_size: int) -> list[list[float]]:
    settings = get_settings()
    config = ProviderConfigDTO(
        provider_type=settings.embedding_provider_type,
        endpoint_url=settings.embedding_endpoint_url,
        model_name=settings.embedding_model_name,
        api_key=settings.embedding_api_key,
    )

    adapter = provider_registry.get(config.provider_type)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = adapter.embed(
            config,
            EmbeddingRequest(model=settings.embedding_model_name, texts=batch),
        )
        if len(response.vectors) != len(batch):
            raise ValueError(f'embedding vector count mismatch: expected={len(batch)} actual={len(response.vectors)}')
        vectors.extend(response.vectors)

    return [normalize_vector_dim([float(x) for x in vec], target_dim) for vec in vectors]


def _get_or_create_local_model(model_name: str, device: str):
    global _local_model, _local_model_key
    model_key = f'{model_name}|{device}'
    with _local_model_lock:
        if _local_model is not None and _local_model_key == model_key:
            return _local_model

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                'sentence-transformers not installed. Run: pip install sentence-transformers'
            ) from exc

        kwargs = {}
        if device and device.lower() != 'auto':
            kwargs['device'] = device
        logger.info(f'[Embedding] Loading model: {model_name}, device: {device}')
        
        try:
            _local_model = SentenceTransformer(model_name, **kwargs)
            logger.info(f'[Embedding] Model loaded successfully: {model_name}')
        except Exception as e:
            # 模型加载失败时抛出异常，让外层捕获并回退到 hash
            raise RuntimeError(f'Failed to load model {model_name}: {str(e)}')
        
        _local_model_key = model_key
        return _local_model


def _embed_with_local_model(texts: list[str], *, target_dim: int, batch_size: int) -> list[list[float]]:
    settings = get_settings()
    model = _get_or_create_local_model(settings.embedding_model_name, settings.embedding_local_device)
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    return [normalize_vector_dim([float(x) for x in vec], target_dim) for vec in vectors]


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    settings = get_settings()
    target_dim = settings.default_embedding_dim
    batch_size = max(1, int(settings.embedding_batch_size))
    backend = str(settings.embedding_backend or 'local').lower()

    try:
        if backend == 'hash':
            return _hash_embed_texts(texts, target_dim)

        if backend == 'local':
            return _embed_with_local_model(texts, target_dim=target_dim, batch_size=batch_size)

        if backend == 'remote':
            if not (settings.embedding_endpoint_url and settings.embedding_endpoint_url.startswith('http')):
                raise ValueError('EMBEDDING_ENDPOINT_URL must be configured when EMBEDDING_BACKEND=remote')
            return _embed_with_remote_provider(texts, target_dim=target_dim, batch_size=batch_size)

        raise ValueError(f'Unsupported EMBEDDING_BACKEND: {settings.embedding_backend}')
    except Exception as exc:
        logger.exception(
            'embedding service failed, backend=%s, fallback=%s, error=%s',
            backend,
            settings.embedding_fallback_hash,
            exc,
        )
        if not settings.embedding_fallback_hash:
            raise
        return _hash_embed_texts(texts, target_dim)


def embed_query(text: str) -> list[float]:
    vectors = embed_texts([text])
    return vectors[0] if vectors else []
