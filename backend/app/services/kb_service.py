from __future__ import annotations

from collections import Counter
import hashlib
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import UUID

import jieba
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Chunk,
    IngestionTask,
    IngestionTaskStatusEnum,
    IngestionTaskTypeEnum,
    KnowledgeEntity,
    KnowledgeFile,
    KnowledgeLibrary,
    KnowledgeLibraryTypeEnum,
    KnowledgeRelation,
    OwnerTypeEnum,
    RoleEnum,
    User,
)
from app.services.graph_service import (
    extract_entities_from_text,
    expand_query_terms_by_graph,
    get_library_graph_snapshot,
    normalize_entity,
    rebuild_library_graph,
    score_merge,
    summarize_graph_sources,
    ZH_STOPWORDS,
    EN_STOPWORDS,
)
from app.services.embedding_service import embed_query, embed_texts
from app.services.retrieval_profile_service import build_runtime_retrieval_config

SUPPORTED_EXTENSIONS = {'.txt', '.md', '.csv'}
ALIAS_INTENT_KEYWORDS = {'外号', '绰号', '称呼', '别名', '又名', '俗称', '法号', '叫什么', '怎么叫', '怎么称呼'}
COREFERENCE_PRONOUNS = {'他', '她', '它', '他们', '她们', '它们', '其', '这个人', '那个人', '这家伙', '那家伙'}
SUMMARY_INTENT_KEYWORDS = {
    '总结', '概述', '归纳', '梳理', '总览', '全貌', '整体', '总体', '全盘', '综述',
    '主要内容', '核心内容', '全书', '整本', '全文', '通篇', '主线', '脉络',
}
COUNT_INTENT_KEYWORDS = {'几个', '多少', '几位', '几人', '几名', '几条', '几种', '几次', '数量'}
ROSTER_INTENT_KEYWORDS = {'徒弟', '弟子', '成员', '角色', '团队', '同伴', '取经团队', '师徒', '班底', '有哪些人'}
ROSTER_SIGNAL_KEYWORDS = {'徒弟', '弟子', '师徒', '成员', '团队', '同伴', '角色', '取经'}
GROUP_CONTEXT_KEYWORDS = {'一起', '同行', '同去', '同往', '随行', '陪同', '团队', '队伍', '同伴', '师徒', '取经'}
QUERY_NOISE_TERMS = {'几个', '多少', '哪些', '什么', '为何', '为什么', '怎么', '如何', '是否', '请问', '一下', '一下子'}
NICKNAME_HINT_PATTERN = re.compile(r'(?:外号|绰号|别名|又名|俗称|法号|叫做|叫作|称作)')
NICKNAME_CALL_PATTERN = re.compile(r'(?:叫|称|唤|骂)[^。！？\n]{0,8}[“"「『]?([\u4e00-\u9fff]{2,5})')
NICKNAME_ADDRESS_PATTERN = re.compile(r'(?:你这|你个|这|那)([\u4e00-\u9fff]{2,4})')
NICKNAME_QUOTED_PATTERN = re.compile(r'[“"「『]([\u4e00-\u9fff]{2,5})[”"」』]')
COUNT_SIGNAL_PATTERN = re.compile(r'([0-9]+|[一二三四五六七八九十百千两俩]+)')
ROSTER_COUNT_PATTERN = re.compile(r'(?:[0-9]+|[一二三四五六七八九十百千两俩]+).{0,4}(?:徒弟|弟子|成员|人|众)')
ROSTER_LIST_PATTERN = re.compile(r'[\u4e00-\u9fff]{2,4}[、和与及][\u4e00-\u9fff]{2,4}')
GRAPH_NEIGHBOR_RELATION_WEIGHTS: dict[str, float] = {
    'contains': 1.25,
    'is_a': 1.10,
    'depends_on': 1.00,
    'causes': 0.90,
    'co_occurs': 0.75,
}
COUNT_UNIT_HINTS = (
    '个', '位', '人', '名', '种', '条', '次', '章', '卷', '岁', '年', '月', '天', '小时', '分钟', '秒',
    '徒弟', '弟子', '成员', '角色', '团队', '队伍', '同伴', '师徒', '众',
)
NICKNAME_TOKEN_BLACKLIST = {
    '师父', '师兄', '师弟', '徒弟', '外号', '别名', '称呼', '名字', '身份', '问题', '答案',
    '这个', '那个', '这些', '那些', '一个', '一种', '事情', '东西', '这里', '那里',
}
ALLOWED_LIBRARY_TYPES = {item.value for item in KnowledgeLibraryTypeEnum}


def create_library(
    db: Session,
    user: User,
    *,
    name: str,
    description: str | None,
    library_type: str | None,
    owner_type: str,
    tags: list[str],
    root_path: str | None,
) -> KnowledgeLibrary:
    try:
        requested_owner = OwnerTypeEnum(owner_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='owner_type must be private or shared') from exc
    if requested_owner == OwnerTypeEnum.shared and user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admin can create shared library')
    normalized_library_type = _normalize_library_type(library_type)

    final_root = _resolve_library_root(root_path, user.id, requested_owner)
    final_root.mkdir(parents=True, exist_ok=True)

    library = KnowledgeLibrary(
        name=name,
        description=description,
        library_type=normalized_library_type,
        owner_type=requested_owner,
        owner_id=user.id,
        tags=tags,
        root_path=str(final_root),
    )
    db.add(library)
    db.commit()
    db.refresh(library)
    return library


def list_libraries(db: Session, user: User) -> list[KnowledgeLibrary]:
    return (
        db.query(KnowledgeLibrary)
        .filter(
            (KnowledgeLibrary.owner_type == OwnerTypeEnum.shared)
            | ((KnowledgeLibrary.owner_type == OwnerTypeEnum.private) & (KnowledgeLibrary.owner_id == user.id))
        )
        .order_by(KnowledgeLibrary.updated_at.desc())
        .all()
    )


def update_library(
    db: Session,
    *,
    library: KnowledgeLibrary,
    user: User,
    name: str | None,
    description: str | None,
    library_type: str | None,
    owner_type: str | None,
    tags: list[str] | None,
) -> KnowledgeLibrary:
    assert_library_access(library, user, write=True)

    if name is not None:
        library.name = name
    if description is not None:
        library.description = description
    if library_type is not None:
        library.library_type = _normalize_library_type(library_type)
    if tags is not None:
        library.tags = tags

    if owner_type is not None and owner_type != library.owner_type.value:
        try:
            new_owner_type = OwnerTypeEnum(owner_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='owner_type must be private or shared',
            ) from exc

        if user.role != RoleEnum.admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Only admin can switch owner_type',
            )
        library.owner_type = new_owner_type
        if new_owner_type == OwnerTypeEnum.private and library.owner_id is None:
            library.owner_id = user.id

    db.add(library)
    db.commit()
    db.refresh(library)
    return library


def delete_library(db: Session, *, library: KnowledgeLibrary, user: User) -> None:
    assert_library_access(library, user, write=True)
    root = Path(library.root_path)
    db.delete(library)
    db.commit()
    if root.exists() and root.is_dir():
        shutil.rmtree(root, ignore_errors=True)


def list_library_files(db: Session, *, library: KnowledgeLibrary, user: User) -> list[KnowledgeFile]:
    assert_library_access(library, user, write=False)
    return (
        db.query(KnowledgeFile)
        .filter(KnowledgeFile.library_id == library.id)
        .order_by(KnowledgeFile.updated_at.desc())
        .all()
    )


def get_file_or_404(db: Session, file_id: UUID) -> KnowledgeFile:
    knowledge_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()
    if not knowledge_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='File not found')
    return knowledge_file


def delete_knowledge_file(db: Session, *, knowledge_file: KnowledgeFile, user: User) -> None:
    import logging
    logger = logging.getLogger('app.request')
    
    library = get_library_or_404(db, knowledge_file.library_id)
    assert_library_access(library, user, write=True)
    path = Path(knowledge_file.filepath)
    library_root = Path(library.root_path).resolve()
    
    # 先删除关联的 chunks（加快删除速度）
    from app.db.models import Chunk
    chunk_count = db.query(Chunk).filter(Chunk.file_id == knowledge_file.id).count()
    logger.info(f'Deleting {chunk_count} chunks for file {knowledge_file.id}')
    db.query(Chunk).filter(Chunk.file_id == knowledge_file.id).delete()
    
    db.delete(knowledge_file)
    db.commit()
    logger.info(f'File {knowledge_file.id} deleted successfully')
    try:
        graph_stats = rebuild_library_graph(db, library.id)
        logger.info(
            f'[Delete] Graph rebuilt after delete: nodes={graph_stats.get("node_count", 0)} edges={graph_stats.get("edge_count", 0)}'
        )
    except Exception as exc:
        logger.warning(f'[Delete] Graph rebuild failed: {exc}')
    
    should_delete_physical = False
    try:
        resolved_path = path.resolve()
        if library_root in resolved_path.parents:
            should_delete_physical = True
    except Exception:
        should_delete_physical = False

    if should_delete_physical and path.exists() and path.is_file():
        path.unlink(missing_ok=True)


def get_library_or_404(db: Session, library_id: UUID) -> KnowledgeLibrary:
    library = db.query(KnowledgeLibrary).filter(KnowledgeLibrary.id == library_id).first()
    if not library:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Library not found')
    return library


def assert_library_access(library: KnowledgeLibrary, user: User, write: bool = False) -> None:
    if library.owner_type == OwnerTypeEnum.shared:
        if write and user.role != RoleEnum.admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admin can modify shared library')
        return
    if library.owner_id != user.id and user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='No access to private library')


def _normalize_library_type(value: str | None) -> str:
    normalized = (value or KnowledgeLibraryTypeEnum.general.value).strip()
    if normalized not in ALLOWED_LIBRARY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='library_type must be one of: general, novel_story, enterprise_docs, scientific_paper, humanities_paper',
        )
    return normalized


def save_uploaded_file(db: Session, *, library: KnowledgeLibrary, uploaded_file: UploadFile) -> KnowledgeFile:
    import logging
    logger = logging.getLogger('app.request')
    
    original_name = Path(uploaded_file.filename or '').name
    ext = Path(original_name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Only txt/md/csv are supported for MVP')

    root = Path(library.root_path)
    root.mkdir(parents=True, exist_ok=True)
    safe_name = original_name or f'file_{datetime.now(timezone.utc).timestamp()}.txt'
    target_path = root / safe_name
    raw = uploaded_file.file.read()
    target_path.write_bytes(raw)
    text = _decode_text(raw)
    logger.info(f'[Upload] File saved: {target_path}')

    knowledge_file = _upsert_knowledge_file(db, library=library, filepath=target_path, text=text)
    logger.info(f'[Upload] Knowledge file created: {knowledge_file.id}')

    # 索引文件内容（向量化）
    try:
        logger.info(f'[Upload] Starting indexing for file: {knowledge_file.id}')
        _reindex_single_file(db, library=library, knowledge_file=knowledge_file, text=text)
        logger.info(f'[Upload] Indexing completed for file: {knowledge_file.id}')
        graph_stats = rebuild_library_graph(db, library.id)
        logger.info(
            f'[Upload] Graph rebuilt: nodes={graph_stats.get("node_count", 0)} edges={graph_stats.get("edge_count", 0)}'
        )
    except Exception as e:
        # 索引失败时清理已创建的文件记录
        db.delete(knowledge_file)
        db.commit()
        logger.error(f'[Upload] Indexing failed: {str(e)}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'索引失败: {str(e)}',
        )

    logger.info(f'[Upload] Upload completed successfully: {knowledge_file.id}')
    return knowledge_file


def sync_directory(
    db: Session,
    *,
    library: KnowledgeLibrary,
    directory_path: str,
    recursive: bool = True,
    triggered_by: User,
) -> IngestionTask:
    settings = get_settings()
    requested_path = Path(directory_path).resolve()
    sync_root = settings.kb_sync_path
    sync_root.mkdir(parents=True, exist_ok=True)

    if sync_root not in requested_path.parents and requested_path != sync_root:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'directory_path must be under configured KB_SYNC_ROOT: {sync_root}',
        )

    if not requested_path.exists() or not requested_path.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Directory does not exist')

    files = _collect_files(requested_path, recursive)
    task = IngestionTask(
        task_type=IngestionTaskTypeEnum.sync_directory,
        status=IngestionTaskStatusEnum.running,
        library_id=library.id,
        created_by=triggered_by.id,
        detail={'directory_path': str(requested_path), 'total_files': len(files)},
        started_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        indexed = 0
        for path in files:
            raw = path.read_bytes()
            text = _decode_text(raw)
            knowledge_file = _upsert_knowledge_file(db, library=library, filepath=path, text=text)
            _reindex_single_file(db, library=library, knowledge_file=knowledge_file, text=text)
            indexed += 1
        graph_stats = rebuild_library_graph(db, library.id)

        task.status = IngestionTaskStatusEnum.completed
        task.detail = {
            **task.detail,
            'indexed_files': indexed,
            'graph_nodes': graph_stats.get('node_count', 0),
            'graph_edges': graph_stats.get('edge_count', 0),
        }
        task.finished_at = datetime.now(timezone.utc)
        db.add(task)
        db.commit()
        db.refresh(task)
    except Exception as exc:
        task.status = IngestionTaskStatusEnum.failed
        task.error_message = str(exc)
        task.finished_at = datetime.now(timezone.utc)
        db.add(task)
        db.commit()
        db.refresh(task)

    return task


def rebuild_index(db: Session, *, library: KnowledgeLibrary, triggered_by: User) -> IngestionTask:
    files = db.query(KnowledgeFile).filter(KnowledgeFile.library_id == library.id).all()
    task = IngestionTask(
        task_type=IngestionTaskTypeEnum.rebuild_index,
        status=IngestionTaskStatusEnum.running,
        library_id=library.id,
        created_by=triggered_by.id,
        detail={'file_count': len(files)},
        started_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        indexed = 0
        for knowledge_file in files:
            path = Path(knowledge_file.filepath)
            if not path.exists():
                continue
            text = _decode_text(path.read_bytes())
            _reindex_single_file(db, library=library, knowledge_file=knowledge_file, text=text)
            indexed += 1
        graph_stats = rebuild_library_graph(db, library.id)

        task.status = IngestionTaskStatusEnum.completed
        task.detail = {
            **task.detail,
            'indexed_files': indexed,
            'graph_nodes': graph_stats.get('node_count', 0),
            'graph_edges': graph_stats.get('edge_count', 0),
        }
        task.finished_at = datetime.now(timezone.utc)
        db.add(task)
        db.commit()
        db.refresh(task)
    except Exception as exc:
        task.status = IngestionTaskStatusEnum.failed
        task.error_message = str(exc)
        task.finished_at = datetime.now(timezone.utc)
        db.add(task)
        db.commit()
        db.refresh(task)

    return task


def get_ingestion_task(db: Session, task_id: UUID) -> IngestionTask:
    task = db.query(IngestionTask).filter(IngestionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    return task


def get_library_graph(db: Session, *, library: KnowledgeLibrary, limit_nodes: int = 80, limit_edges: int = 150) -> dict:
    return get_library_graph_snapshot(
        db,
        library.id,
        limit_nodes=max(10, min(limit_nodes, 300)),
        limit_edges=max(10, min(limit_edges, 500)),
    )


def rebuild_library_graph_index(db: Session, *, library: KnowledgeLibrary) -> dict:
    return rebuild_library_graph(db, library.id)


def hybrid_search(
    db: Session,
    *,
    library_ids: list[UUID],
    query: str,
    top_k: int = 5,
    history_context: list[str] | None = None,
    retrieval_profile: dict | None = None,
) -> list[dict]:
    if not library_ids:
        return []

    settings = get_settings()
    runtime_config = build_runtime_retrieval_config(retrieval_profile, settings)
    summary_mode = bool(runtime_config.get('summary_intent_enabled', True)) and is_global_summary_query(query)
    summary_expand_factor = max(1, min(int(runtime_config.get('summary_expand_factor', 3)), 8))
    summary_min_chunks = max(4, min(int(runtime_config.get('summary_min_chunks', 8)), 24))
    effective_top_k = max(top_k, summary_min_chunks if summary_mode else top_k)
    if summary_mode:
        effective_top_k = max(effective_top_k, top_k * summary_expand_factor)

    vector_multiplier = max(2, min(int(runtime_config.get('vector_candidate_multiplier', 4)), 20))
    keyword_multiplier = max(2, min(int(runtime_config.get('keyword_candidate_multiplier', 4)), 20))
    graph_multiplier = max(2, min(int(runtime_config.get('graph_candidate_multiplier', 5)), 24))
    if not summary_mode:
        # 非总结问题保持较小候选池，避免噪声片段挤占 top_k
        vector_multiplier = min(vector_multiplier, 3)
        keyword_multiplier = min(keyword_multiplier, 3)
        graph_multiplier = min(graph_multiplier, 4)

    # 获取知识库中所有实体，用于查询扩展
    all_entities = (
        db.query(KnowledgeEntity)
        .filter(KnowledgeEntity.library_id.in_(library_ids))
        .all()
    )
    entities_by_name = {e.name: e for e in all_entities}
    entities_by_id = {e.id: e for e in all_entities}
    entities_by_display: dict[str, list[KnowledgeEntity]] = {}
    entities_by_alias: dict[str, list[KnowledgeEntity]] = {}
    for entity in all_entities:
        display_norm = normalize_entity(entity.display_name)
        entities_by_display.setdefault(display_norm, []).append(entity)
        aliases = (entity.metadata_json or {}).get('aliases', [])
        if isinstance(aliases, list):
            for alias in aliases:
                alias_norm = normalize_entity(str(alias))
                if alias_norm:
                    entities_by_alias.setdefault(alias_norm, []).append(entity)
    
    # 提取查询中的实体
    query_entities = _extract_entities_for_search(query, limit=10)
    count_intent = _is_count_intent_query(query)
    roster_intent = _is_roster_intent_query(query) or _is_group_count_query(query)
    count_unit_hints = _extract_count_unit_hints(query)
    
    # 从历史对话中提取实体，用于增强当前查询
    history_entities: list[str] = []
    if history_context:
        for hist_msg in history_context[-4:]:  # 最近4条消息
            extracted = _extract_entities_for_search(hist_msg, limit=6)
            history_entities = _merge_entities_preserve_order(history_entities, extracted, limit=15)

    context_entities = _select_context_entities(
        query,
        query_entities=query_entities,
        history_entities=history_entities,
        enable_coreference=bool(runtime_config.get('co_reference_enabled', True)),
        enable_alias_intent=bool(runtime_config.get('alias_intent_enabled', True)),
    )
    query_for_embedding = _build_contextual_query(query, context_entities)
    query_embedding = embed_query(query_for_embedding)
    
    # 合并当前查询实体和历史实体
    all_entities_for_search = _merge_entities_preserve_order(query_entities, history_entities, limit=20)
    all_entities_for_search = _merge_entities_preserve_order(all_entities_for_search, context_entities, limit=22)
    
    # 构建扩展查询词：原始查询 + 实体名 + 别名
    all_query_terms = [query]
    if query_for_embedding != query:
        all_query_terms.append(query_for_embedding)
    for qe in all_entities_for_search:
        qe_norm = normalize_entity(qe)
        if not qe_norm:
            continue
        matched_entities: list[KnowledgeEntity] = []
        direct = entities_by_name.get(qe_norm)
        if direct:
            matched_entities.append(direct)
        matched_entities.extend(entities_by_display.get(qe_norm, []))
        matched_entities.extend(entities_by_alias.get(qe_norm, []))

        for entity in matched_entities:
            all_query_terms.append(entity.name)
            all_query_terms.append(entity.display_name)
            aliases = (entity.metadata_json or {}).get('aliases', [])
            if isinstance(aliases, list):
                all_query_terms.extend(str(alias) for alias in aliases if alias)

    # 增加普通关键词分词（不仅仅是实体），解决非实体关键词检索遗漏问题
    raw_keywords = jieba.cut_for_search(query)
    for k in raw_keywords:
        k = k.strip()
        if len(k) >= 2 and k.lower() not in EN_STOPWORDS and k not in ZH_STOPWORDS:
            all_query_terms.append(k)
    
    # 去重
    all_query_terms = list(set(all_query_terms))
    keyword_queries = _filter_keyword_queries(all_query_terms, max_terms=64)
    if count_intent and roster_intent:
        keyword_queries = _merge_entities_preserve_order(
            keyword_queries,
            ['师徒', '徒弟', '成员', '团队', '同伴', '同行', '取经'],
            limit=64,
        )
    keyword_term_set = _normalize_search_terms(keyword_queries)
    query_focus_terms = _normalize_search_terms(
        [
            token.strip()
            for token in jieba.cut_for_search(query)
            if token.strip() and len(normalize_entity(token.strip())) >= 2
        ],
        max_terms=8,
    )
    anchor_term_set = _build_anchor_terms(
        query_entities,
        context_entities,
        query_focus_terms,
        max_terms=16 if roster_intent else 12,
    )

    vector_distance_expr = Chunk.embedding.cosine_distance(query_embedding).label('vector_distance')
    vector_candidates = (
        db.query(Chunk, KnowledgeFile.filename, vector_distance_expr)
        .join(KnowledgeFile, Chunk.file_id == KnowledgeFile.id)
        .filter(Chunk.library_id.in_(library_ids))
        .order_by(vector_distance_expr)
        .limit(max(top_k * vector_multiplier, effective_top_k * 2, 16))
        .all()
    )

    # 关键词检索：使用原始查询 + 扩展查询词
    keyword_filters = [Chunk.content.ilike(f'%{term}%') for term in keyword_queries]
    keyword_candidates = []
    if keyword_filters:
        keyword_scan_cap = max(top_k * keyword_multiplier * 6, effective_top_k * 6, 120)
        if count_intent:
            keyword_scan_cap = max(keyword_scan_cap, 360)
        if roster_intent:
            keyword_scan_cap = max(keyword_scan_cap, 900)
        keyword_raw_candidates = (
            db.query(Chunk, KnowledgeFile.filename)
            .join(KnowledgeFile, Chunk.file_id == KnowledgeFile.id)
            .filter(Chunk.library_id.in_(library_ids), or_(*keyword_filters))
            .limit(min(keyword_scan_cap, 5000))
            .all()
        )
        rescored_candidates = []
        for chunk, filename in keyword_raw_candidates:
            local_score = _score_keyword_candidate(
                content=chunk.content,
                keyword_term_set=keyword_term_set,
                anchor_term_set=anchor_term_set,
                count_intent=count_intent,
                roster_intent=roster_intent,
                count_unit_hints=count_unit_hints,
            )
            if local_score <= 0.0:
                continue
            rescored_candidates.append((local_score, chunk, filename))
        rescored_candidates.sort(key=lambda row: row[0], reverse=True)
        keep_size = max(top_k * keyword_multiplier, effective_top_k * 2, 20)
        keyword_candidates = [(chunk, filename) for _, chunk, filename in rescored_candidates[:keep_size]]

    graph_expansion = expand_query_terms_by_graph(
        db,
        library_ids=library_ids,
        query=query_for_embedding,
        max_terms=max(6, min(int(runtime_config.get('rag_graph_max_terms', 12)), 24)),
    )
    graph_terms = graph_expansion.get('expanded_terms', [])
    graph_matches = graph_expansion.get('matched_entities', [])

    alias_mined_terms: list[str] = []
    if bool(runtime_config.get('alias_intent_enabled', True)) and _is_alias_intent_query(query):
        anchor_entity_terms = _merge_entities_preserve_order(graph_matches, all_entities_for_search, limit=12)
        alias_mined_terms = _mine_alias_terms_from_entity_chunks(
            db,
            library_ids=library_ids,
            entity_terms=anchor_entity_terms,
            max_terms=max(0, min(int(runtime_config.get('alias_mining_max_terms', 8)), 24)),
        )
        if alias_mined_terms:
            graph_terms = _merge_entities_preserve_order(
                graph_terms,
                alias_mined_terms,
                limit=int(runtime_config.get('rag_graph_max_terms', 12)) * 2,
            )

    roster_mined_terms: list[str] = []
    if roster_intent:
        roster_seed_terms = _merge_entities_preserve_order(graph_matches, all_entities_for_search, limit=14)
        roster_mined_terms = _mine_related_terms_by_graph_neighbors(
            db,
            library_ids=library_ids,
            seed_terms=roster_seed_terms,
            entities_by_id=entities_by_id,
            entities_by_name=entities_by_name,
            entities_by_display=entities_by_display,
            entities_by_alias=entities_by_alias,
            max_terms=max(4, min(int(runtime_config.get('rag_graph_max_terms', 12)), 16)),
        )
        if roster_mined_terms:
            graph_terms = _merge_entities_preserve_order(
                graph_terms,
                roster_mined_terms,
                limit=int(runtime_config.get('rag_graph_max_terms', 12)) * 3,
            )
            keyword_queries = _merge_entities_preserve_order(keyword_queries, roster_mined_terms, limit=48)
            keyword_term_set = _normalize_search_terms(keyword_queries, max_terms=48)
            anchor_term_set = _normalize_search_terms(
                _merge_entities_preserve_order(anchor_term_set, roster_mined_terms, limit=16),
                max_terms=16,
            )

            roster_filters = [Chunk.content.ilike(f'%{term}%') for term in roster_mined_terms[:10]]
            if roster_filters:
                roster_raw_candidates = (
                    db.query(Chunk, KnowledgeFile.filename)
                    .join(KnowledgeFile, Chunk.file_id == KnowledgeFile.id)
                    .filter(Chunk.library_id.in_(library_ids), or_(*roster_filters))
                    .limit(max(top_k * keyword_multiplier * 6, effective_top_k * 6, 240))
                    .all()
                )
                roster_rescored: list[tuple[float, Chunk, str]] = []
                for chunk, filename in roster_raw_candidates:
                    local_score = _score_keyword_candidate(
                        content=chunk.content,
                        keyword_term_set=keyword_term_set,
                        anchor_term_set=anchor_term_set,
                        count_intent=count_intent,
                        roster_intent=True,
                        count_unit_hints=count_unit_hints,
                    )
                    if local_score <= 0.0:
                        continue
                    roster_rescored.append((local_score, chunk, filename))
                roster_rescored.sort(key=lambda row: row[0], reverse=True)
                existing_chunk_ids = {str(chunk.id) for chunk, _ in keyword_candidates}
                for _, chunk, filename in roster_rescored[: max(effective_top_k * 5, 40)]:
                    chunk_key = str(chunk.id)
                    if chunk_key in existing_chunk_ids:
                        continue
                    keyword_candidates.append((chunk, filename))
                    existing_chunk_ids.add(chunk_key)

    # 图谱通道仅使用图谱扩展词，避免与 keyword 通道重复放大噪声
    all_search_terms = list(set(graph_terms))
    graph_term_set = _normalize_search_terms(all_search_terms)
    matched_entity_terms = _normalize_search_terms(_merge_entities_preserve_order(graph_matches, context_entities, limit=16))
    graph_filters = [Chunk.content.ilike(f'%{term}%') for term in all_search_terms if term and len(term.strip()) >= 2]
    graph_candidates = []
    if graph_filters:
        graph_candidates = (
            db.query(Chunk, KnowledgeFile.filename)
            .join(KnowledgeFile, Chunk.file_id == KnowledgeFile.id)
            .filter(Chunk.library_id.in_(library_ids), or_(*graph_filters))
            .limit(max(top_k * graph_multiplier, effective_top_k * 3, 20))
            .all()
        )

    merged: dict[str, dict] = {}

    for rank, (chunk, filename, distance) in enumerate(vector_candidates):
        key = str(chunk.id)
        vector_score, vector_similarity = _score_vector_candidate(distance, rank)
        merged[key] = _serialize_chunk_result(
            chunk,
            filename,
            vector_score,
            source='vector',
            matched_entities=graph_matches,
            vector_similarity=vector_similarity,
            keyword_overlap=0.0,
            graph_overlap=0.0,
            entity_overlap=0.0,
        )

    for rank, (chunk, filename) in enumerate(keyword_candidates):
        key = str(chunk.id)
        keyword_overlap = _term_hit_ratio(chunk.content, keyword_term_set)
        anchor_overlap = _term_hit_ratio(chunk.content, anchor_term_set)
        score = _score_sparse_candidate(rank, keyword_overlap, entity_boost=anchor_overlap, channel_weight=1.0)
        if key in merged:
            merged[key]['score'] = score_merge(float(merged[key]['score']), score)
            merged[key]['source'] = summarize_graph_sources([str(merged[key]['source']), 'keyword'])
            merged[key]['keyword_overlap'] = max(float(merged[key].get('keyword_overlap', 0.0)), keyword_overlap)
            merged[key]['anchor_overlap'] = max(float(merged[key].get('anchor_overlap', 0.0)), anchor_overlap)
        else:
            merged[key] = _serialize_chunk_result(
                chunk,
                filename,
                score,
                source='keyword',
                matched_entities=graph_matches,
                vector_similarity=0.0,
                keyword_overlap=keyword_overlap,
                graph_overlap=0.0,
                entity_overlap=anchor_overlap,
            )
            merged[key]['anchor_overlap'] = round(float(anchor_overlap), 6)

    for rank, (chunk, filename) in enumerate(graph_candidates):
        key = str(chunk.id)
        graph_overlap = _term_hit_ratio(chunk.content, graph_term_set)
        entity_overlap = _term_hit_ratio(chunk.content, matched_entity_terms)
        base_keyword_overlap = _term_hit_ratio(chunk.content, keyword_term_set)
        score = _score_sparse_candidate(
            rank,
            graph_overlap,
            entity_boost=entity_overlap,
            channel_weight=float(runtime_config.get('graph_channel_weight', 0.65)),
        )
        if base_keyword_overlap == 0.0 and entity_overlap == 0.0:
            # 只命中图谱扩展词但没命中原问题词/实体时，降权避免伪命中
            score = round(score * float(runtime_config.get('graph_only_penalty', 0.55)), 6)
        if key in merged:
            merged[key]['score'] = score_merge(float(merged[key]['score']), score)
            merged[key]['source'] = summarize_graph_sources([str(merged[key]['source']), 'graph'])
            merged[key]['graph_overlap'] = max(float(merged[key].get('graph_overlap', 0.0)), graph_overlap)
            merged[key]['entity_overlap'] = max(float(merged[key].get('entity_overlap', 0.0)), entity_overlap)
        else:
            merged[key] = _serialize_chunk_result(
                chunk,
                filename,
                score,
                source='graph',
                matched_entities=graph_matches,
                vector_similarity=0.0,
                keyword_overlap=0.0,
                graph_overlap=graph_overlap,
                entity_overlap=entity_overlap,
                )

    for item in merged.values():
        focus_overlap = _term_hit_ratio(str(item.get('snippet') or ''), query_focus_terms)
        anchor_overlap = _term_hit_ratio(str(item.get('snippet') or ''), anchor_term_set)
        count_boost = (
            0.08
            if count_intent and _has_count_signal(str(item.get('snippet') or ''), unit_hints=count_unit_hints)
            else 0.0
        )
        roster_boost = 0.10 if roster_intent and _has_roster_signal(str(item.get('snippet') or ''), anchor_term_set) else 0.0
        item['query_focus_overlap'] = round(float(focus_overlap), 6)
        item['anchor_overlap'] = round(max(float(item.get('anchor_overlap') or 0.0), float(anchor_overlap)), 6)
        if focus_overlap > 0.0 or anchor_overlap > 0.0 or count_boost > 0.0 or roster_boost > 0.0:
            refined = round(
                (0.20 * float(focus_overlap))
                + (0.24 * float(anchor_overlap))
                + float(count_boost)
                + float(roster_boost),
                6,
            )
            item['score'] = score_merge(float(item.get('score') or 0.0), refined)

        if anchor_term_set and not summary_mode and float(item.get('anchor_overlap') or 0.0) == 0.0:
            # 对“问题实体完全不相关”的片段做降权，避免西游前期噪声挤占名额。
            item['score'] = round(float(item.get('score') or 0.0) * 0.72, 6)

    ordered = sorted(merged.values(), key=lambda item: item['score'], reverse=True)
    hits = _finalize_retrieval_hits(
        ordered,
        top_k=effective_top_k,
        runtime_config=runtime_config,
        summary_mode=summary_mode,
        count_intent=count_intent,
        roster_intent=roster_intent,
        count_unit_hints=count_unit_hints,
    )
    if hits:
        if _should_expand_to_keyword_fallback(
            hits,
            runtime_config=runtime_config,
            anchor_term_set=anchor_term_set,
            count_intent=count_intent,
            roster_intent=roster_intent,
            count_unit_hints=count_unit_hints,
            summary_mode=summary_mode,
        ):
            fallback_hits = _fulltext_keyword_fallback_search(
                db,
                library_ids=library_ids,
                top_k=effective_top_k,
                keyword_queries=keyword_queries,
                keyword_term_set=keyword_term_set,
                anchor_term_set=anchor_term_set,
                count_intent=count_intent,
                roster_intent=roster_intent,
                count_unit_hints=count_unit_hints,
                matched_entities=graph_matches,
                runtime_config=runtime_config,
            )
            if fallback_hits:
                return _merge_retrieval_results(
                    hits,
                    fallback_hits,
                    max_items=int(runtime_config.get('keyword_fallback_max_chunks', 240)),
                )
        return hits

    if not bool(runtime_config.get('fallback_relax_enabled', True)):
        return []

    relaxed_runtime = _build_relaxed_runtime_config(runtime_config)
    relaxed_hits = _finalize_retrieval_hits(
        ordered,
        top_k=effective_top_k,
        runtime_config=relaxed_runtime,
        summary_mode=summary_mode,
        allow_lenient=True,
        count_intent=count_intent,
        roster_intent=roster_intent,
        count_unit_hints=count_unit_hints,
    )
    if relaxed_hits:
        return relaxed_hits

    return _fulltext_keyword_fallback_search(
        db,
        library_ids=library_ids,
        top_k=effective_top_k,
        keyword_queries=keyword_queries,
        keyword_term_set=keyword_term_set,
        anchor_term_set=anchor_term_set,
        count_intent=count_intent,
        roster_intent=roster_intent,
        count_unit_hints=count_unit_hints,
        matched_entities=graph_matches,
        runtime_config=runtime_config,
    )


def _serialize_chunk_result(
    chunk: Chunk,
    filename: str,
    score: float,
    source: str,
    matched_entities: list[str] | None = None,
    vector_similarity: float = 0.0,
    keyword_overlap: float = 0.0,
    graph_overlap: float = 0.0,
    entity_overlap: float = 0.0,
) -> dict:
    return {
        'chunk_id': chunk.id,
        'file_id': chunk.file_id,
        'library_id': chunk.library_id,
        'file_name': filename,
        'snippet': chunk.content[:500],
        'score': round(float(score), 6),
        'source': source,
        'matched_entities': matched_entities or [],
        'vector_similarity': round(float(vector_similarity), 6),
        'keyword_overlap': round(float(keyword_overlap), 6),
        'graph_overlap': round(float(graph_overlap), 6),
        'entity_overlap': round(float(entity_overlap), 6),
        'anchor_overlap': 0.0,
        'query_focus_overlap': 0.0,
    }


def _merge_entities_preserve_order(primary: list[str], secondary: list[str], *, limit: int = 20) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for source in (primary, secondary):
        for item in source:
            cleaned = str(item).strip()
            norm = normalize_entity(cleaned)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            merged.append(cleaned)
            if len(merged) >= limit:
                return merged
    return merged


def _extract_entities_for_search(text: str, *, limit: int = 10) -> list[str]:
    entities = extract_entities_from_text(text, max_entities=limit)
    if len(entities) >= limit:
        return entities[:limit]

    for token in jieba.cut_for_search(text):
        token = token.strip()
        norm = normalize_entity(token)
        if len(norm) < 2 or len(norm) > 8:
            continue
        if norm in EN_STOPWORDS or norm in ZH_STOPWORDS:
            continue
        entities = _merge_entities_preserve_order(entities, [token], limit=limit)
        if len(entities) >= limit:
            break
    return entities


def _is_alias_intent_query(query: str) -> bool:
    normalized = normalize_entity(query)
    return any(keyword in query or keyword in normalized for keyword in ALIAS_INTENT_KEYWORDS)


def is_global_summary_query(query: str) -> bool:
    if not query:
        return False
    normalized = normalize_entity(query)
    if any(keyword in query or keyword in normalized for keyword in SUMMARY_INTENT_KEYWORDS):
        return True
    # 常见问法：请整体介绍X/完整梳理X
    if re.search(r'(整体|完整|全面|系统).{0,4}(介绍|梳理|说明|总结)', query):
        return True
    return False


def _is_count_intent_query(query: str) -> bool:
    if not query:
        return False
    normalized = normalize_entity(query)
    if any(keyword in query or keyword in normalized for keyword in COUNT_INTENT_KEYWORDS):
        return True
    return bool(re.search(r'(几|多少).{0,4}(个|位|人|名|种|条|次|章|卷)', query))


def _is_group_count_query(query: str) -> bool:
    if not query:
        return False
    if not _is_count_intent_query(query):
        return False
    if any(keyword in query for keyword in GROUP_CONTEXT_KEYWORDS):
        return True
    return bool(re.search(r'(几|多少).{0,2}(个|位|人|名).{0,6}(一起|同行|团队|队伍|同伴|师徒|取经)', query))


def _is_roster_intent_query(query: str) -> bool:
    if not query:
        return False
    normalized = normalize_entity(query)
    if any(keyword in query or keyword in normalized for keyword in ROSTER_INTENT_KEYWORDS):
        return True
    return bool(
        re.search(r'(哪些|哪几|都有谁|由谁|包括谁|分别是|名单).{0,6}(徒弟|弟子|成员|角色|人物|团队|同伴|师徒)', query)
    )


def _extract_count_unit_hints(query: str) -> list[str]:
    if not query:
        return []
    hints: list[str] = []
    for unit in COUNT_UNIT_HINTS:
        if unit in query:
            hints.append(unit)
    return _merge_entities_preserve_order(hints, [], limit=10)


def _has_count_signal(text: str, *, unit_hints: list[str] | None = None) -> bool:
    if not text:
        return False
    if unit_hints:
        for unit in unit_hints[:8]:
            if re.search(rf'([0-9]+|[一二三四五六七八九十百千两俩]+)\s*{re.escape(unit)}', text):
                return True
        if any(unit in {'徒弟', '弟子', '成员', '角色', '团队', '同伴', '师徒', '众', '人'} for unit in unit_hints):
            if ROSTER_COUNT_PATTERN.search(text):
                return True
        return False
    return bool(COUNT_SIGNAL_PATTERN.search(text))


def _has_roster_signal(text: str, anchor_terms: list[str] | None = None) -> bool:
    if not text:
        return False
    if ROSTER_COUNT_PATTERN.search(text):
        return True
    if any(keyword in text for keyword in ROSTER_SIGNAL_KEYWORDS):
        if ROSTER_LIST_PATTERN.search(text):
            return True
        if anchor_terms:
            hit_count = sum(1 for term in anchor_terms[:10] if term and term in text)
            if hit_count >= 2:
                return True
    if anchor_terms:
        anchor_hit_count = sum(1 for term in anchor_terms[:10] if term and term in text)
        if anchor_hit_count >= 3:
            return True
    return False


def _contains_coreference_pronoun(query: str) -> bool:
    return any(token in query for token in COREFERENCE_PRONOUNS)


def _select_context_entities(
    query: str,
    *,
    query_entities: list[str],
    history_entities: list[str],
    enable_coreference: bool = True,
    enable_alias_intent: bool = True,
) -> list[str]:
    context_entities: list[str] = []
    recent_history = list(reversed(history_entities[-4:]))

    if enable_coreference and _contains_coreference_pronoun(query):
        context_entities = _merge_entities_preserve_order(context_entities, recent_history, limit=4)

    if enable_alias_intent and _is_alias_intent_query(query):
        context_entities = _merge_entities_preserve_order(context_entities, recent_history, limit=5)

    if not query_entities and recent_history:
        context_entities = _merge_entities_preserve_order(context_entities, recent_history[:2], limit=5)

    return context_entities


def _build_contextual_query(query: str, context_entities: list[str]) -> str:
    if not context_entities:
        return query
    query_entities = {normalize_entity(item) for item in _extract_entities_for_search(query, limit=8)}
    suffix_terms = [term for term in context_entities if normalize_entity(term) not in query_entities]
    suffix = ' '.join(suffix_terms[:3]).strip()
    if not suffix:
        return query
    return f'{query} {suffix}'.strip()


def _is_valid_nickname_term(token: str) -> bool:
    norm = normalize_entity(token)
    if len(norm) < 2 or len(norm) > 5:
        return False
    if not re.fullmatch(r'[\u4e00-\u9fff]{2,5}', norm):
        return False
    if norm in EN_STOPWORDS or norm in ZH_STOPWORDS or norm in NICKNAME_TOKEN_BLACKLIST:
        return False
    if any(bad in norm for bad in ('外号', '别名', '称呼', '名字')):
        return False
    return True


def _extract_nickname_candidates(text: str) -> list[str]:
    if not text:
        return []

    candidates: list[str] = []

    if NICKNAME_HINT_PATTERN.search(text):
        for match in NICKNAME_CALL_PATTERN.finditer(text):
            token = match.group(1).strip()
            if _is_valid_nickname_term(token):
                candidates.append(token)

    for match in NICKNAME_ADDRESS_PATTERN.finditer(text):
        token = match.group(1).strip()
        left_context = text[max(0, match.start() - 8) : match.start()]
        if not re.search(r'(道|骂|叫|称|唤|喊|喝)', left_context):
            continue
        if _is_valid_nickname_term(token):
            candidates.append(token)

    for match in NICKNAME_QUOTED_PATTERN.finditer(text):
        token = match.group(1).strip()
        left_context = text[max(0, match.start() - 10) : match.start()]
        if not re.search(r'(道|骂|叫|称|唤|喊|喝)', left_context):
            continue
        if _is_valid_nickname_term(token):
            candidates.append(token)

    return _merge_entities_preserve_order(candidates, [], limit=12)


def _mine_alias_terms_from_entity_chunks(
    db: Session,
    *,
    library_ids: list[UUID],
    entity_terms: list[str],
    max_terms: int = 8,
) -> list[str]:
    normalized_entity_terms = _normalize_search_terms(entity_terms, max_terms=10)
    if not normalized_entity_terms:
        return []

    filters = [Chunk.content.ilike(f'%{term}%') for term in normalized_entity_terms[:6]]
    if not filters:
        return []

    rows = (
        db.query(Chunk.content)
        .filter(Chunk.library_id.in_(library_ids), or_(*filters))
        .limit(120)
        .all()
    )

    entity_norm_set = {normalize_entity(item) for item in normalized_entity_terms}
    counter: Counter[str] = Counter()
    for (content,) in rows:
        for candidate in _extract_nickname_candidates(content):
            norm = normalize_entity(candidate)
            if norm in entity_norm_set:
                continue
            counter[candidate] += 1

    ranked = sorted(counter.items(), key=lambda item: (item[1], len(item[0])), reverse=True)
    results = [term for term, _ in ranked[:max_terms]]
    return _merge_entities_preserve_order(results, [], limit=max_terms)


def _mine_related_terms_by_graph_neighbors(
    db: Session,
    *,
    library_ids: list[UUID],
    seed_terms: list[str],
    entities_by_id: dict[UUID, KnowledgeEntity],
    entities_by_name: dict[str, KnowledgeEntity],
    entities_by_display: dict[str, list[KnowledgeEntity]],
    entities_by_alias: dict[str, list[KnowledgeEntity]],
    max_terms: int = 8,
) -> list[str]:
    normalized_seed_terms = _normalize_search_terms(seed_terms, max_terms=16)
    if not normalized_seed_terms or max_terms <= 0:
        return []

    seed_entities: dict[UUID, KnowledgeEntity] = {}
    for term in normalized_seed_terms:
        direct = entities_by_name.get(term)
        if direct:
            seed_entities[direct.id] = direct
        for item in entities_by_display.get(term, []):
            seed_entities[item.id] = item
        for item in entities_by_alias.get(term, []):
            seed_entities[item.id] = item
    if not seed_entities:
        return []

    seed_id_set = set(seed_entities.keys())
    relation_rows = (
        db.query(KnowledgeRelation)
        .filter(
            KnowledgeRelation.library_id.in_(library_ids),
            or_(
                KnowledgeRelation.source_entity_id.in_(list(seed_id_set)),
                KnowledgeRelation.target_entity_id.in_(list(seed_id_set)),
            ),
        )
        .order_by(KnowledgeRelation.weight.desc())
        .limit(260)
        .all()
    )
    if not relation_rows:
        return []

    related_scores: Counter[UUID] = Counter()
    for relation in relation_rows:
        candidate_id: UUID | None = None
        if relation.source_entity_id in seed_id_set and relation.target_entity_id not in seed_id_set:
            candidate_id = relation.target_entity_id
        elif relation.target_entity_id in seed_id_set and relation.source_entity_id not in seed_id_set:
            candidate_id = relation.source_entity_id
        if candidate_id is None:
            continue
        relation_factor = GRAPH_NEIGHBOR_RELATION_WEIGHTS.get(str(relation.relation_type), 0.75)
        related_scores[candidate_id] += max(1.0, float(relation.weight)) * relation_factor

    if not related_scores:
        return []

    seed_norm_set = {normalize_entity(term) for term in normalized_seed_terms}
    mined_terms: list[str] = []
    for entity_id, _ in related_scores.most_common(max_terms * 4):
        entity = entities_by_id.get(entity_id)
        if entity is None:
            continue
        candidate_terms = [entity.display_name]
        aliases = (entity.metadata_json or {}).get('aliases', [])
        if isinstance(aliases, list):
            candidate_terms.extend(str(alias) for alias in aliases[:2] if alias)
        for candidate in candidate_terms:
            norm = normalize_entity(candidate)
            if len(norm) < 2:
                continue
            if norm in seed_norm_set or norm in EN_STOPWORDS or norm in ZH_STOPWORDS or norm in QUERY_NOISE_TERMS:
                continue
            mined_terms = _merge_entities_preserve_order(mined_terms, [candidate], limit=max_terms)
            if len(mined_terms) >= max_terms:
                return mined_terms
    return mined_terms


def _filter_keyword_queries(terms: list[str], *, max_terms: int = 64) -> list[str]:
    filtered: list[str] = []
    seen: set[str] = set()
    for term in terms:
        raw = str(term).strip()
        norm = normalize_entity(raw)
        if len(norm) < 2:
            continue
        if norm in seen:
            continue
        if norm in QUERY_NOISE_TERMS or norm in EN_STOPWORDS or norm in ZH_STOPWORDS:
            continue
        seen.add(norm)
        filtered.append(raw)
        if len(filtered) >= max_terms:
            break
    return filtered


def _normalize_search_terms(terms: list[str], *, max_terms: int = 28) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for term in terms:
        norm = normalize_entity(str(term))
        if len(norm) < 2:
            continue
        if norm in seen:
            continue
        seen.add(norm)
        normalized.append(norm)
        if len(normalized) >= max_terms:
            break
    return normalized


def _build_anchor_terms(
    query_entities: list[str],
    context_entities: list[str],
    query_focus_terms: list[str],
    *,
    max_terms: int = 12,
) -> list[str]:
    max_terms = max(6, min(max_terms, 24))
    terms = _merge_entities_preserve_order(query_entities, context_entities, limit=max_terms)
    for token in query_focus_terms:
        norm = normalize_entity(token)
        if len(norm) < 2:
            continue
        if norm in QUERY_NOISE_TERMS:
            continue
        terms = _merge_entities_preserve_order(terms, [norm], limit=max_terms)
    return _normalize_search_terms(terms, max_terms=max_terms)


def _score_keyword_candidate(
    *,
    content: str,
    keyword_term_set: list[str],
    anchor_term_set: list[str],
    count_intent: bool,
    roster_intent: bool,
    count_unit_hints: list[str] | None = None,
) -> float:
    keyword_overlap = _term_hit_ratio(content, keyword_term_set)
    anchor_overlap = _term_hit_ratio(content, anchor_term_set)
    count_boost = 0.10 if count_intent and _has_count_signal(content, unit_hints=count_unit_hints) else 0.0
    roster_boost = 0.10 if roster_intent and _has_roster_signal(content, anchor_term_set) else 0.0
    return round((0.52 * keyword_overlap) + (0.32 * anchor_overlap) + count_boost + roster_boost, 6)


def _fulltext_keyword_fallback_search(
    db: Session,
    *,
    library_ids: list[UUID],
    top_k: int,
    keyword_queries: list[str],
    keyword_term_set: list[str],
    anchor_term_set: list[str],
    count_intent: bool,
    roster_intent: bool,
    count_unit_hints: list[str] | None = None,
    matched_entities: list[str] | None = None,
    runtime_config: dict | None = None,
) -> list[dict]:
    # 作为图谱/混合检索 miss 的最后兜底：按关键词覆盖度做全文候选扫描。
    runtime_config = runtime_config or build_runtime_retrieval_config(None)
    keyword_fallback_max_chunks = max(20, min(int(runtime_config.get('keyword_fallback_max_chunks', 240)), 800))
    keyword_fallback_min_score = max(0.0, min(float(runtime_config.get('keyword_fallback_min_score', 0.08)), 1.5))
    keyword_fallback_scan_limit = max(200, min(int(runtime_config.get('keyword_fallback_scan_limit', 8000)), 20000))

    search_terms = _merge_entities_preserve_order(anchor_term_set, keyword_queries, limit=32)
    filters = [Chunk.content.ilike(f'%{term}%') for term in search_terms if len(normalize_entity(term)) >= 2]
    if not filters:
        return []

    rows = (
        db.query(Chunk, KnowledgeFile.filename)
        .join(KnowledgeFile, Chunk.file_id == KnowledgeFile.id)
        .filter(Chunk.library_id.in_(library_ids), or_(*filters))
        .limit(
            min(
                max(
                    top_k * 30,
                    220,
                    720 if count_intent else 0,
                    1200 if roster_intent else 0,
                ),
                keyword_fallback_scan_limit,
            )
        )
        .all()
    )
    if not rows:
        return []

    rescored: list[tuple[float, Chunk, str, float, float]] = []
    for chunk, filename in rows:
        keyword_overlap = _term_hit_ratio(chunk.content, keyword_term_set)
        anchor_overlap = _term_hit_ratio(chunk.content, anchor_term_set)
        if anchor_term_set and anchor_overlap == 0.0 and keyword_overlap < 0.25:
            continue
        score = _score_keyword_candidate(
            content=chunk.content,
            keyword_term_set=keyword_term_set,
            anchor_term_set=anchor_term_set,
            count_intent=count_intent,
            roster_intent=roster_intent,
            count_unit_hints=count_unit_hints,
        )
        if score < keyword_fallback_min_score:
            continue
        rescored.append((score, chunk, filename, keyword_overlap, anchor_overlap))

    rescored.sort(key=lambda item: item[0], reverse=True)
    if not rescored:
        return []

    results: list[dict] = []
    used_chunk_ids: set[str] = set()
    for score, chunk, filename, keyword_overlap, anchor_overlap in rescored:
        chunk_key = str(chunk.id)
        if chunk_key in used_chunk_ids:
            continue
        used_chunk_ids.add(chunk_key)
        row = _serialize_chunk_result(
            chunk,
            filename,
            max(0.16, score),  # fallback 通道保留基础分，避免被 min_item 直接裁掉
            source='keyword_fallback',
            matched_entities=matched_entities or [],
            vector_similarity=0.0,
            keyword_overlap=keyword_overlap,
            graph_overlap=0.0,
            entity_overlap=anchor_overlap,
        )
        row['anchor_overlap'] = round(float(anchor_overlap), 6)
        row['query_focus_overlap'] = round(float(keyword_overlap), 6)
        results.append(row)
        if len(results) >= keyword_fallback_max_chunks:
            break

    return results


def _should_expand_to_keyword_fallback(
    hits: list[dict],
    *,
    runtime_config: dict,
    anchor_term_set: list[str],
    count_intent: bool,
    roster_intent: bool,
    count_unit_hints: list[str] | None,
    summary_mode: bool,
) -> bool:
    if not hits or summary_mode:
        return False
    if not bool(runtime_config.get('keyword_fallback_expand_on_weak_hits', True)):
        return False

    window = hits[: min(len(hits), 8)]
    top_anchor = max(float(item.get('anchor_overlap') or 0.0) for item in window)
    if anchor_term_set and top_anchor == 0.0:
        return True

    if count_intent:
        has_count_evidence = any(
            _has_count_signal(str(item.get('snippet') or ''), unit_hints=count_unit_hints) for item in window
        )
        if not has_count_evidence:
            return True

    if roster_intent:
        has_roster_evidence = any(
            _has_roster_signal(str(item.get('snippet') or ''), anchor_term_set) for item in window
        )
        if not has_roster_evidence:
            return True

    weak_lexical_hits = sum(
        1
        for item in window
        if float(item.get('keyword_overlap') or 0.0) >= 0.12 or float(item.get('anchor_overlap') or 0.0) >= 0.10
    )
    top1_score = float(window[0].get('score') or 0.0)
    rag_min_top1 = float(runtime_config.get('rag_min_top1_score', 0.30))
    return weak_lexical_hits <= 1 and top1_score < rag_min_top1 + 0.05


def _merge_retrieval_results(primary: list[dict], secondary: list[dict], *, max_items: int) -> list[dict]:
    merged: list[dict] = []
    seen_chunk_ids: set[str] = set()
    max_items = max(5, min(max_items, 800))

    for source in (primary, secondary):
        for item in source:
            chunk_id = str(item.get('chunk_id') or '')
            if not chunk_id or chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            merged.append(item)
            if len(merged) >= max_items:
                return merged

    return merged


def _term_hit_ratio(text: str, normalized_terms: list[str]) -> float:
    if not text or not normalized_terms:
        return 0.0
    haystack = text.lower()
    hit_count = sum(1 for term in normalized_terms if term and term.lower() in haystack)
    denominator = max(1, min(len(normalized_terms), 8))
    return round(min(1.0, hit_count / denominator), 6)


def _score_vector_candidate(distance: float | None, rank: int) -> tuple[float, float]:
    safe_distance = 1.0 if distance is None else max(0.0, float(distance))
    vector_similarity = max(0.0, min(1.0, 1.0 - safe_distance))
    rank_signal = 1.0 / (rank + 1)
    score = (0.85 * vector_similarity) + (0.15 * rank_signal)
    return round(score, 6), round(vector_similarity, 6)


def _score_sparse_candidate(rank: int, hit_ratio: float, *, entity_boost: float, channel_weight: float) -> float:
    rank_signal = 1.0 / (rank + 1)
    raw_score = (0.55 * float(hit_ratio)) + (0.35 * rank_signal) + (0.10 * float(entity_boost))
    return round(float(channel_weight) * raw_score, 6)


def _is_retrieval_hit(candidates: list[dict], *, runtime_config: dict | None = None) -> bool:
    runtime_config = runtime_config or build_runtime_retrieval_config(None)
    if not candidates:
        return False

    rag_min_top1_score = float(runtime_config.get('rag_min_top1_score', 0.30))
    rag_min_support_score = float(runtime_config.get('rag_min_support_score', 0.18))
    rag_min_support_count = int(runtime_config.get('rag_min_support_count', 2))
    vector_semantic_min = float(runtime_config.get('vector_semantic_min', 0.12))

    top1_score = float(candidates[0].get('score') or 0.0)
    support_count = sum(1 for item in candidates if float(item.get('score') or 0.0) >= rag_min_support_score)
    if top1_score < rag_min_top1_score:
        return False
    if support_count < rag_min_support_count and top1_score < rag_min_top1_score + 0.15:
        return False

    window = candidates[: max(3, rag_min_support_count)]
    lexical_signal = any(float(item.get('keyword_overlap') or 0.0) > 0.0 for item in window)
    entity_signal = any(float(item.get('entity_overlap') or 0.0) > 0.0 for item in window)
    graph_signal = any(float(item.get('graph_overlap') or 0.0) > 0.0 for item in window)
    anchor_signal = any(float(item.get('anchor_overlap') or 0.0) > 0.0 for item in window)
    query_focus_signal = any(float(item.get('query_focus_overlap') or 0.0) > 0.0 for item in window)
    semantic_signal = float(candidates[0].get('vector_similarity') or 0.0) >= vector_semantic_min

    # 图谱信号必须与实体或语义信号之一同时出现，避免“只靠图谱词”误命中
    if lexical_signal or entity_signal or anchor_signal or query_focus_signal:
        return True
    if graph_signal and semantic_signal:
        return True
    return semantic_signal and top1_score >= rag_min_top1_score + 0.08


def _finalize_retrieval_hits(
    ordered: list[dict],
    *,
    top_k: int,
    runtime_config: dict | None = None,
    summary_mode: bool = False,
    allow_lenient: bool = False,
    count_intent: bool = False,
    roster_intent: bool = False,
    count_unit_hints: list[str] | None = None,
) -> list[dict]:
    runtime_config = runtime_config or build_runtime_retrieval_config(None)
    if not ordered:
        return []
    min_item_score = float(runtime_config.get('rag_min_item_score', 0.10))
    rag_min_support_count = int(runtime_config.get('rag_min_support_count', 2))
    pruned = [item for item in ordered if float(item.get('score') or 0.0) >= min_item_score]
    if not pruned:
        return []

    validation_window = pruned[: max(top_k * 2, rag_min_support_count + 1)]
    hit_ok = _is_retrieval_hit(validation_window, runtime_config=runtime_config)
    if not hit_ok:
        summary_lenient = summary_mode and allow_lenient and _has_summary_signals(validation_window, runtime_config)
        general_lenient = allow_lenient and _has_lenient_hit_signals(
            validation_window,
            runtime_config=runtime_config,
            count_intent=count_intent,
            roster_intent=roster_intent,
            count_unit_hints=count_unit_hints,
        )
        if not (summary_lenient or general_lenient):
            return []

    if summary_mode:
        return _select_diverse_hits(
            pruned,
            top_k=top_k,
            per_file_cap=int(runtime_config.get('summary_per_file_cap', 2)),
            min_files=int(runtime_config.get('summary_min_files', 3)),
        )
    return pruned[:top_k]


def _build_relaxed_runtime_config(runtime_config: dict) -> dict:
    def clamp_float(value: object, *, fallback: float, lower: float, upper: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = fallback
        return max(lower, min(upper, parsed))

    top1_relax = clamp_float(runtime_config.get('fallback_top1_relax'), fallback=0.08, lower=0.0, upper=0.30)
    support_relax = clamp_float(runtime_config.get('fallback_support_relax'), fallback=0.06, lower=0.0, upper=0.30)
    item_relax = clamp_float(runtime_config.get('fallback_item_relax'), fallback=0.04, lower=0.0, upper=0.20)
    relaxed = dict(runtime_config)
    relaxed['rag_min_top1_score'] = max(0.0, float(runtime_config.get('rag_min_top1_score', 0.30)) - top1_relax)
    relaxed['rag_min_support_score'] = max(0.0, float(runtime_config.get('rag_min_support_score', 0.18)) - support_relax)
    relaxed['rag_min_item_score'] = max(0.0, float(runtime_config.get('rag_min_item_score', 0.10)) - item_relax)
    relaxed['rag_min_support_count'] = max(1, int(runtime_config.get('rag_min_support_count', 2)) - 1)
    relaxed['vector_semantic_min'] = max(0.0, float(runtime_config.get('vector_semantic_min', 0.12)) - (support_relax * 0.5))
    return relaxed


def _has_summary_signals(candidates: list[dict], runtime_config: dict) -> bool:
    if not candidates:
        return False
    vector_floor = max(0.0, float(runtime_config.get('vector_semantic_min', 0.12)) * 0.8)
    lexical_hits = sum(
        1
        for item in candidates
        if float(item.get('keyword_overlap') or 0.0) > 0.0 or float(item.get('entity_overlap') or 0.0) > 0.0
    )
    semantic_hits = sum(1 for item in candidates if float(item.get('vector_similarity') or 0.0) >= vector_floor)
    file_span = len({str(item.get('file_id') or item.get('file_name') or '') for item in candidates})
    avg_score = sum(float(item.get('score') or 0.0) for item in candidates) / max(1, len(candidates))
    return lexical_hits >= 1 or semantic_hits >= 2 or (file_span >= 2 and avg_score >= float(runtime_config.get('rag_min_item_score', 0.10)))


def _has_lenient_hit_signals(
    candidates: list[dict],
    *,
    runtime_config: dict,
    count_intent: bool = False,
    roster_intent: bool = False,
    count_unit_hints: list[str] | None = None,
) -> bool:
    if not candidates:
        return False
    window = candidates[:8]
    vector_floor = max(0.0, float(runtime_config.get('vector_semantic_min', 0.12)) * 0.85)
    for item in window:
        focus_overlap = float(item.get('query_focus_overlap') or 0.0)
        keyword_overlap = float(item.get('keyword_overlap') or 0.0)
        entity_overlap = float(item.get('entity_overlap') or 0.0)
        anchor_overlap = float(item.get('anchor_overlap') or 0.0)
        vector_similarity = float(item.get('vector_similarity') or 0.0)
        snippet = str(item.get('snippet') or '')

        if focus_overlap >= 0.22 and (keyword_overlap > 0.0 or entity_overlap > 0.0 or anchor_overlap > 0.0 or vector_similarity >= vector_floor):
            return True
        if keyword_overlap >= 0.20 and (entity_overlap >= 0.08 or anchor_overlap >= 0.08):
            return True
        if count_intent and _has_count_signal(snippet, unit_hints=count_unit_hints):
            if focus_overlap >= 0.15 or keyword_overlap >= 0.12 or entity_overlap >= 0.08 or anchor_overlap >= 0.08:
                return True
        if roster_intent and _has_roster_signal(snippet):
            if focus_overlap >= 0.12 or keyword_overlap >= 0.10 or entity_overlap >= 0.08 or anchor_overlap >= 0.08:
                return True
    return False


def _select_diverse_hits(
    candidates: list[dict],
    *,
    top_k: int,
    per_file_cap: int = 2,
    min_files: int = 3,
) -> list[dict]:
    if not candidates:
        return []
    per_file_cap = max(1, min(per_file_cap, 6))
    min_files = max(1, min(min_files, 10))

    buckets: dict[str, list[dict]] = {}
    for item in candidates:
        file_key = str(item.get('file_id') or item.get('file_name') or item.get('chunk_id'))
        buckets.setdefault(file_key, []).append(item)

    sorted_files = sorted(
        buckets.items(),
        key=lambda pair: float(pair[1][0].get('score') or 0.0),
        reverse=True,
    )

    selected: list[dict] = []
    used_chunk_ids: set[str] = set()
    taken_per_file: dict[str, int] = {}

    target_coverage = min(len(sorted_files), min_files, top_k)
    for file_key, items in sorted_files:
        if len(selected) >= target_coverage:
            break
        candidate = items[0]
        chunk_key = str(candidate.get('chunk_id'))
        if chunk_key in used_chunk_ids:
            continue
        selected.append(candidate)
        used_chunk_ids.add(chunk_key)
        taken_per_file[file_key] = 1

    progress = True
    while len(selected) < top_k and progress:
        progress = False
        for file_key, items in sorted_files:
            used_count = taken_per_file.get(file_key, 0)
            if used_count >= per_file_cap:
                continue
            if used_count >= len(items):
                continue
            candidate = items[used_count]
            chunk_key = str(candidate.get('chunk_id'))
            taken_per_file[file_key] = used_count + 1
            if chunk_key in used_chunk_ids:
                continue
            selected.append(candidate)
            used_chunk_ids.add(chunk_key)
            progress = True
            if len(selected) >= top_k:
                break

    if len(selected) < top_k:
        for candidate in candidates:
            chunk_key = str(candidate.get('chunk_id'))
            if chunk_key in used_chunk_ids:
                continue
            selected.append(candidate)
            used_chunk_ids.add(chunk_key)
            if len(selected) >= top_k:
                break

    return selected[:top_k]


def _resolve_library_root(root_path: str | None, user_id: UUID, owner_type: OwnerTypeEnum) -> Path:
    settings = get_settings()
    base = settings.storage_path / 'libraries'
    if owner_type == OwnerTypeEnum.shared:
        base = base / 'shared'
    else:
        base = base / str(user_id)

    if root_path:
        requested = Path(root_path)
        if not requested.is_absolute():
            requested = base / requested
        resolved = requested.resolve()
        storage_root = settings.storage_path.resolve()
        if storage_root not in resolved.parents and resolved != storage_root:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'root_path must be under storage root: {storage_root}',
            )
        return resolved
    return (base / datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')).resolve()


def _collect_files(root: Path, recursive: bool) -> list[Path]:
    iterator: Iterable[Path] = root.rglob('*') if recursive else root.glob('*')
    files = []
    for path in iterator:
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        files.append(path)
    return files


def _decode_text(raw: bytes) -> str:
    for encoding in ('utf-8', 'utf-8-sig', 'gb18030', 'gbk', 'latin-1'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='ignore')


def _upsert_knowledge_file(db: Session, *, library: KnowledgeLibrary, filepath: Path, text: str) -> KnowledgeFile:
    content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    existing = (
        db.query(KnowledgeFile)
        .filter(KnowledgeFile.library_id == library.id, KnowledgeFile.filepath == str(filepath.resolve()))
        .first()
    )
    if existing:
        existing.content_hash = content_hash
        existing.status = 'indexed'
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    created = KnowledgeFile(
        library_id=library.id,
        filename=filepath.name,
        filepath=str(filepath.resolve()),
        file_type=filepath.suffix.lstrip('.').lower() or 'txt',
        content_hash=content_hash,
        status='indexed',
    )
    db.add(created)
    db.commit()
    db.refresh(created)
    return created


def _split_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, 0)
    return chunks


def _reindex_single_file(db: Session, *, library: KnowledgeLibrary, knowledge_file: KnowledgeFile, text: str) -> None:
    db.query(Chunk).filter(Chunk.file_id == knowledge_file.id).delete()

    chunks = _split_text(text)
    embeddings = embed_texts(chunks)
    for index, chunk_text in enumerate(chunks):
        vector = embeddings[index] if index < len(embeddings) else embed_query(chunk_text)
        chunk = Chunk(
            library_id=library.id,
            file_id=knowledge_file.id,
            chunk_index=index,
            content=chunk_text,
            embedding=vector,
            metadata_json={'length': len(chunk_text)},
        )
        db.add(chunk)
    db.commit()
