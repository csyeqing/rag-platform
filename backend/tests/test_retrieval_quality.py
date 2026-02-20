from app.services.kb_service import (
    _build_contextual_query,
    _extract_nickname_candidates,
    _finalize_retrieval_hits,
    _is_alias_intent_query,
    _normalize_search_terms,
    _score_vector_candidate,
    _select_diverse_hits,
    _select_context_entities,
    _term_hit_ratio,
    is_global_summary_query,
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


def test_alias_intent_query_detected() -> None:
    assert _is_alias_intent_query('孙悟空还叫过他什么外号？')


def test_contextual_query_appends_recent_entity_for_pronoun() -> None:
    context_entities = _select_context_entities(
        '孙悟空还叫过他什么外号？',
        query_entities=['孙悟空'],
        history_entities=['猪八戒', '八戒'],
    )
    contextual_query = _build_contextual_query('孙悟空还叫过他什么外号？', context_entities)
    assert '猪八戒' in contextual_query or '八戒' in contextual_query


def test_extract_nickname_candidates_from_dialogue() -> None:
    text = '行者骂道：“你这呆子，快走！”'
    candidates = _extract_nickname_candidates(text)
    assert '呆子' in candidates


def test_global_summary_query_detected() -> None:
    assert is_global_summary_query('请你全面总结一下这本书的主线和人物关系')


def test_select_diverse_hits_spreads_across_files() -> None:
    candidates = [
        {'chunk_id': 'a1', 'file_id': 'file_a', 'score': 0.90},
        {'chunk_id': 'a2', 'file_id': 'file_a', 'score': 0.88},
        {'chunk_id': 'a3', 'file_id': 'file_a', 'score': 0.86},
        {'chunk_id': 'b1', 'file_id': 'file_b', 'score': 0.80},
        {'chunk_id': 'b2', 'file_id': 'file_b', 'score': 0.78},
        {'chunk_id': 'c1', 'file_id': 'file_c', 'score': 0.76},
    ]
    selected = _select_diverse_hits(candidates, top_k=4, per_file_cap=2, min_files=3)
    assert len(selected) == 4
    file_ids = {item['file_id'] for item in selected}
    assert {'file_a', 'file_b', 'file_c'}.issubset(file_ids)


def test_finalize_retrieval_hits_summary_mode_uses_multi_source() -> None:
    candidates = [
        {'chunk_id': 'a1', 'file_id': 'file_a', 'score': 0.82, 'keyword_overlap': 0.4, 'entity_overlap': 0.2, 'vector_similarity': 0.35},
        {'chunk_id': 'a2', 'file_id': 'file_a', 'score': 0.79, 'keyword_overlap': 0.3, 'entity_overlap': 0.1, 'vector_similarity': 0.31},
        {'chunk_id': 'a3', 'file_id': 'file_a', 'score': 0.75, 'keyword_overlap': 0.2, 'entity_overlap': 0.1, 'vector_similarity': 0.28},
        {'chunk_id': 'b1', 'file_id': 'file_b', 'score': 0.62, 'keyword_overlap': 0.2, 'entity_overlap': 0.0, 'vector_similarity': 0.20},
        {'chunk_id': 'c1', 'file_id': 'file_c', 'score': 0.58, 'keyword_overlap': 0.1, 'entity_overlap': 0.0, 'vector_similarity': 0.18},
    ]
    result = _finalize_retrieval_hits(candidates, top_k=4, summary_mode=True)
    assert len(result) == 4
    file_ids = {item['file_id'] for item in result}
    assert {'file_a', 'file_b', 'file_c'}.issubset(file_ids)
