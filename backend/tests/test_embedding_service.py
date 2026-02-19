from types import SimpleNamespace

from app.services import embedding_service


def test_normalize_vector_dim_pad_and_truncate() -> None:
    padded = embedding_service.normalize_vector_dim([1.0, 2.0], 4)
    assert padded == [1.0, 2.0, 0.0, 0.0]

    truncated = embedding_service.normalize_vector_dim([1.0, 2.0, 3.0], 2)
    assert truncated == [1.0, 2.0]


def test_embed_texts_fallback_to_hash_when_endpoint_empty(monkeypatch) -> None:
    fake_settings = SimpleNamespace(
        embedding_backend='remote',
        default_embedding_dim=8,
        embedding_provider_type='openai_compatible',
        embedding_endpoint_url='',
        embedding_model_name='BAAI/bge-m3',
        embedding_api_key='',
        embedding_local_device='auto',
        embedding_batch_size=4,
        embedding_fallback_hash=True,
    )
    monkeypatch.setattr(embedding_service, 'get_settings', lambda: fake_settings)

    vectors = embedding_service.embed_texts(['RAG', '知识库'])
    assert len(vectors) == 2
    assert len(vectors[0]) == 8
    assert len(vectors[1]) == 8


def test_embed_texts_local_mode_uses_local_encoder(monkeypatch) -> None:
    fake_settings = SimpleNamespace(
        embedding_backend='local',
        default_embedding_dim=6,
        embedding_provider_type='openai_compatible',
        embedding_endpoint_url='',
        embedding_model_name='BAAI/bge-m3',
        embedding_api_key='',
        embedding_local_device='auto',
        embedding_batch_size=4,
        embedding_fallback_hash=True,
    )
    monkeypatch.setattr(embedding_service, 'get_settings', lambda: fake_settings)
    monkeypatch.setattr(
        embedding_service,
        '_embed_with_local_model',
        lambda texts, target_dim, batch_size: [[1.0] * target_dim for _ in texts],
    )

    vectors = embedding_service.embed_texts(['A', 'B'])
    assert vectors == [[1.0] * 6, [1.0] * 6]
