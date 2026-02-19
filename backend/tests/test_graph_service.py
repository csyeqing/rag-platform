from app.services.graph_service import (
    extract_entities_from_text,
    extract_relations_from_text,
    infer_relation_type,
    normalize_entity,
)


def test_extract_entities_from_text_mixed_language() -> None:
    text = 'RAG 系统使用 Elasticsearch 与 PostgreSQL 构建企业知识检索。'
    entities = extract_entities_from_text(text)
    normalized = [normalize_entity(item) for item in entities]
    assert 'rag' in normalized
    assert any('elasticsearch' == item for item in normalized)
    assert any('postgresql' == item for item in normalized)


def test_infer_relation_type_contains() -> None:
    sentence = '知识库包括产品文档和运维手册。'
    assert infer_relation_type(sentence) == 'contains'


def test_extract_relations_from_text_returns_pairs() -> None:
    text = 'RAG 依赖 Embedding 模型和向量数据库。向量数据库包括 pgvector 与 Milvus。'
    relations = extract_relations_from_text(text)
    assert len(relations) > 0
    relation_types = {item[2] for item in relations}
    assert 'depends_on' in relation_types or 'contains' in relation_types or 'co_occurs' in relation_types
