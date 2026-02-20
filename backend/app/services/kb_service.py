from __future__ import annotations

import hashlib
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
    OwnerTypeEnum,
    RoleEnum,
    User,
)
from app.services.graph_service import (
    expand_query_terms_by_graph,
    get_library_graph_snapshot,
    rebuild_library_graph,
    score_merge,
    summarize_graph_sources,
    ZH_STOPWORDS,
    EN_STOPWORDS,
)
from app.services.embedding_service import embed_query, embed_texts

SUPPORTED_EXTENSIONS = {'.txt', '.md', '.csv'}


def create_library(db: Session, user: User, *, name: str, description: str | None, owner_type: str, tags: list[str], root_path: str | None) -> KnowledgeLibrary:
    try:
        requested_owner = OwnerTypeEnum(owner_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='owner_type must be private or shared') from exc
    if requested_owner == OwnerTypeEnum.shared and user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admin can create shared library')

    final_root = _resolve_library_root(root_path, user.id, requested_owner)
    final_root.mkdir(parents=True, exist_ok=True)

    library = KnowledgeLibrary(
        name=name,
        description=description,
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
    owner_type: str | None,
    tags: list[str] | None,
) -> KnowledgeLibrary:
    assert_library_access(library, user, write=True)

    if name is not None:
        library.name = name
    if description is not None:
        library.description = description
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
) -> list[dict]:
    if not library_ids:
        return []

    query_embedding = embed_query(query)

    # 获取知识库中所有实体，用于查询扩展
    all_entities = (
        db.query(KnowledgeEntity)
        .filter(KnowledgeEntity.library_id.in_(library_ids))
        .all()
    )
    entity_map = {e.name: e.display_name for e in all_entities}
    
    # 提取查询中的实体
    from app.services.graph_service import extract_entities_from_text, TITLE_SUFFIXES
    query_entities = extract_entities_from_text(query, max_entities=10)
    
    # 从历史对话中提取实体，用于增强当前查询
    history_entities: list[str] = []
    if history_context:
        for hist_msg in history_context[-4:]:  # 最近4条消息
            extracted = extract_entities_from_text(hist_msg, max_entities=5)
            history_entities.extend(extracted)
        history_entities = list(set(history_entities))[:15]  # 去重，最多15个
    
    # 合并当前查询实体和历史实体
    all_entities_for_search = list(set(query_entities + history_entities))
    
    # 构建扩展查询词：原始查询 + 所有实体的已知别名
    all_query_terms = [query]
    for qe in all_entities_for_search:
        qe_norm = qe.lower() if qe else ""
        # 如果实体是某个知识库实体的别名，添加正式名
        for ent_name, ent_display in entity_map.items():
            if ent_name == qe_norm or ent_display == qe:
                all_query_terms.append(ent_name)
                all_query_terms.append(ent_display)

    # 增加普通关键词分词（不仅仅是实体），解决非实体关键词检索遗漏问题
    raw_keywords = jieba.cut_for_search(query)
    for k in raw_keywords:
        k = k.strip()
        if len(k) >= 2 and k.lower() not in EN_STOPWORDS and k not in ZH_STOPWORDS:
            all_query_terms.append(k)
    
    # 去重
    all_query_terms = list(set(all_query_terms))

    vector_candidates = (
        db.query(Chunk, KnowledgeFile.filename)
        .join(KnowledgeFile, Chunk.file_id == KnowledgeFile.id)
        .filter(Chunk.library_id.in_(library_ids))
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(max(top_k * 2, 10))
        .all()
    )

    # 关键词检索：使用原始查询 + 扩展查询词
    keyword_queries = [term for term in all_query_terms if term and len(term) >= 2]
    keyword_filters = [Chunk.content.ilike(f'%{term}%') for term in keyword_queries]
    keyword_candidates = []
    if keyword_filters:
        keyword_candidates = (
            db.query(Chunk, KnowledgeFile.filename)
            .join(KnowledgeFile, Chunk.file_id == KnowledgeFile.id)
            .filter(Chunk.library_id.in_(library_ids), or_(*keyword_filters))
            .limit(max(top_k * 2, 10))
            .all()
        )

    graph_expansion = expand_query_terms_by_graph(db, library_ids=library_ids, query=query, max_terms=8)
    graph_terms = graph_expansion.get('expanded_terms', [])
    graph_matches = graph_expansion.get('matched_entities', [])
    # 也将图谱扩展词加入检索
    all_search_terms = list(set(keyword_queries + graph_terms))
    graph_filters = [Chunk.content.ilike(f'%{term}%') for term in all_search_terms if term and len(term.strip()) >= 2]
    graph_candidates = []
    if graph_filters:
        graph_candidates = (
            db.query(Chunk, KnowledgeFile.filename)
            .join(KnowledgeFile, Chunk.file_id == KnowledgeFile.id)
            .filter(Chunk.library_id.in_(library_ids), or_(*graph_filters))
            .limit(max(top_k * 3, 12))
            .all()
        )

    merged: dict[str, dict] = {}

    for rank, (chunk, filename) in enumerate(vector_candidates):
        key = str(chunk.id)
        score = 1.0 / (rank + 1)
        merged[key] = _serialize_chunk_result(
            chunk,
            filename,
            score,
            source='vector',
            matched_entities=graph_matches,
        )

    for rank, (chunk, filename) in enumerate(keyword_candidates):
        key = str(chunk.id)
        score = 1.0 / (rank + 1)
        if key in merged:
            merged[key]['score'] = score_merge(float(merged[key]['score']), score)
            merged[key]['source'] = summarize_graph_sources([str(merged[key]['source']), 'keyword'])
        else:
            merged[key] = _serialize_chunk_result(
                chunk,
                filename,
                score,
                source='keyword',
                matched_entities=graph_matches,
            )

    for rank, (chunk, filename) in enumerate(graph_candidates):
        key = str(chunk.id)
        score = 0.8 / (rank + 1)
        if key in merged:
            merged[key]['score'] = score_merge(float(merged[key]['score']), score)
            merged[key]['source'] = summarize_graph_sources([str(merged[key]['source']), 'graph'])
        else:
            merged[key] = _serialize_chunk_result(
                chunk,
                filename,
                score,
                source='graph',
                matched_entities=graph_matches,
            )

    ordered = sorted(merged.values(), key=lambda item: item['score'], reverse=True)
    return ordered[:top_k]


def _serialize_chunk_result(
    chunk: Chunk,
    filename: str,
    score: float,
    source: str,
    matched_entities: list[str] | None = None,
) -> dict:
    return {
        'chunk_id': chunk.id,
        'file_id': chunk.file_id,
        'library_id': chunk.library_id,
        'file_name': filename,
        'snippet': chunk.content[:500],
        'score': score,
        'source': source,
        'matched_entities': matched_entities or [],
    }


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
