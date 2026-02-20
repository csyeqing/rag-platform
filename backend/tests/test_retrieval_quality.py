from app.services.kb_service import (
    _finalize_retrieval_hits,
    _normalize_search_terms,
    _score_vector_candidate,
    _term_hit_ratio,
)


def test_normalize_search_terms_dedup() -> None:
    terms = _normalize_search_terms(['悟能', '八戒', '悟能', '  八戒  ', 'a', ''])
    assert terms == ['悟能', '八戒']


def test_term_hit_ratio_matches_alias_terms() -> None:
    content = '猪八戒也叫悟能，是取经队伍的重要成员。'
    terms = _normalize_search_terms(['猪八戒', '悟能', '沙僧'])
    ratio = _term_hit_ratio(content, terms)
    assert ratio > 0


def test_score_vector_candidate_prefers_lower_distance() -> None:
    high_score, high_sim = _score_vector_candidate(0.15, 0)
    low_score, low_sim = _score_vector_candidate(0.75, 0)
    assert high_score > low_score
    assert high_sim > low_sim


def test_finalize_retrieval_hits_accepts_strong_signal() -> None:
    candidates = [
        {
            'score': 0.61,
            'keyword_overlap': 0.25,
            'graph_overlap': 0.0,
            'entity_overlap': 0.0,
            'vector_similarity': 0.21,
        },
        {
            'score': 0.33,
            'keyword_overlap': 0.12,
            'graph_overlap': 0.0,
            'entity_overlap': 0.0,
            'vector_similarity': 0.12,
        },
        {
            'score': 0.14,
            'keyword_overlap': 0.0,
            'graph_overlap': 0.0,
            'entity_overlap': 0.0,
            'vector_similarity': 0.1,
        },
    ]
    result = _finalize_retrieval_hits(candidates, top_k=2)
    assert len(result) == 2


def test_finalize_retrieval_hits_filters_pseudo_hits() -> None:
    pseudo_candidates = [
        {
            'score': 0.41,
            'keyword_overlap': 0.0,
            'graph_overlap': 0.0,
            'entity_overlap': 0.0,
            'vector_similarity': 0.05,
        },
        {
            'score': 0.27,
            'keyword_overlap': 0.0,
            'graph_overlap': 0.0,
            'entity_overlap': 0.0,
            'vector_similarity': 0.06,
        },
    ]
    result = _finalize_retrieval_hits(pseudo_candidates, top_k=2)
    assert result == []
