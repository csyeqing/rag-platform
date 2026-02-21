from app.services.kb_service import (
    _build_contextual_query,
    _filter_keyword_queries,
    _extract_nickname_candidates,
    _finalize_retrieval_hits,
    _has_count_signal,
    _has_roster_signal,
    _is_alias_intent_query,
    _is_count_intent_query,
    _is_group_count_query,
    _is_roster_intent_query,
    _merge_retrieval_results,
    _normalize_search_terms,
    _score_keyword_candidate,
    _score_vector_candidate,
    _select_diverse_hits,
    _select_context_entities,
    _should_expand_to_keyword_fallback,
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


def test_count_intent_detected() -> None:
    assert _is_count_intent_query('唐僧有几个徒弟？')
    assert _has_count_signal('唐僧有三个徒弟，分别是孙悟空、猪八戒、沙僧。')


def test_group_count_query_detected() -> None:
    assert _is_group_count_query('唐僧和几个人一起去取经？')


def test_filter_keyword_queries_removes_noise_terms() -> None:
    terms = _filter_keyword_queries(['唐僧', '几个', '多少', '取经', '一起', '请问'])
    assert '唐僧' in terms
    assert '取经' in terms
    assert '几个' not in terms
    assert '多少' not in terms


def test_roster_intent_detected() -> None:
    assert _is_roster_intent_query('唐僧取经团队包括哪些角色？')


def test_roster_signal_detected() -> None:
    assert _has_roster_signal(
        '唐僧同悟空、悟能、悟净，牵马挑担，师徒四众继续西行。',
        ['唐僧', '悟空', '悟能', '悟净'],
    )


def test_keyword_score_boosted_for_roster_signal() -> None:
    content = '师徒四众：唐僧、悟空、悟能、悟净同往西天取经。'
    base_score = _score_keyword_candidate(
        content=content,
        keyword_term_set=['唐僧', '徒弟'],
        anchor_term_set=['唐僧', '悟空', '悟能', '悟净'],
        count_intent=True,
        roster_intent=False,
    )
    boosted_score = _score_keyword_candidate(
        content=content,
        keyword_term_set=['唐僧', '徒弟'],
        anchor_term_set=['唐僧', '悟空', '悟能', '悟净'],
        count_intent=True,
        roster_intent=True,
    )
    assert boosted_score > base_score


def test_finalize_retrieval_hits_lenient_for_count_query() -> None:
    candidates = [
        {
            'score': 0.24,
            'keyword_overlap': 0.12,
            'graph_overlap': 0.0,
            'entity_overlap': 0.10,
            'query_focus_overlap': 0.34,
            'vector_similarity': 0.09,
            'snippet': '唐僧有三个徒弟：孙悟空、猪八戒、沙僧。',
            'file_id': 'x',
            'chunk_id': 'x1',
        },
        {
            'score': 0.19,
            'keyword_overlap': 0.08,
            'graph_overlap': 0.0,
            'entity_overlap': 0.05,
            'query_focus_overlap': 0.20,
            'vector_similarity': 0.08,
            'snippet': '此处提到唐僧与其徒弟同行西行。',
            'file_id': 'y',
            'chunk_id': 'y1',
        },
    ]
    result = _finalize_retrieval_hits(candidates, top_k=2, allow_lenient=True, count_intent=True)
    assert len(result) >= 1


def test_count_signal_with_unit_hints_filters_noise_number() -> None:
    age_sentence = '那老僧说，我今年二百七十岁，怎么得做个唐僧。'
    assert not _has_count_signal(age_sentence, unit_hints=['人', '徒弟'])
    assert _has_count_signal('唐僧有三个人一起去取经。', unit_hints=['人'])


def test_finalize_retrieval_hits_lenient_for_roster_query() -> None:
    candidates = [
        {
            'score': 0.21,
            'keyword_overlap': 0.10,
            'graph_overlap': 0.0,
            'entity_overlap': 0.08,
            'query_focus_overlap': 0.14,
            'anchor_overlap': 0.10,
            'vector_similarity': 0.07,
            'snippet': '师徒四众同行，唐僧同悟空、悟能、悟净一路西行。',
            'file_id': 'm',
            'chunk_id': 'm1',
        },
    ]
    result = _finalize_retrieval_hits(candidates, top_k=1, allow_lenient=True, roster_intent=True)
    assert len(result) == 1


def test_should_expand_to_keyword_fallback_for_weak_count_hits() -> None:
    hits = [
        {
            'score': 0.31,
            'keyword_overlap': 0.10,
            'anchor_overlap': 0.20,
            'snippet': '唐僧一路前行，路途遥远。',
        }
    ]
    assert _should_expand_to_keyword_fallback(
        hits,
        runtime_config={'keyword_fallback_expand_on_weak_hits': True, 'rag_min_top1_score': 0.30},
        anchor_term_set=['唐僧', '徒弟'],
        count_intent=True,
        roster_intent=True,
        count_unit_hints=['人', '徒弟'],
        summary_mode=False,
    )


def test_merge_retrieval_results_deduplicates_chunk_id() -> None:
    primary = [{'chunk_id': 'a', 'score': 0.8}, {'chunk_id': 'b', 'score': 0.7}]
    secondary = [{'chunk_id': 'b', 'score': 0.9}, {'chunk_id': 'c', 'score': 0.6}]
    merged = _merge_retrieval_results(primary, secondary, max_items=10)
    assert [item['chunk_id'] for item in merged] == ['a', 'b', 'c']
