from app.services.providers.local_algorithms import hash_embedding, token_overlap_score


def test_hash_embedding_dimension() -> None:
    vec = hash_embedding('hello world', dim=16)
    assert len(vec) == 16


def test_token_overlap_score_order() -> None:
    high = token_overlap_score('rag architecture', 'rag architecture and pipeline')
    low = token_overlap_score('rag architecture', 'totally unrelated text')
    assert high > low
