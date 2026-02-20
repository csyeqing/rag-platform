from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import ChatMessage, ChatRoleEnum, ChatSession, KnowledgeLibrary, OwnerTypeEnum, ProviderConfig, RoleEnum, User
from app.services.kb_service import hybrid_search
from app.services.provider_service import to_runtime_config
from app.services.providers.base import ChatRequest, ProviderConfigDTO, RerankRequest
from app.services.providers.registry import provider_registry


def create_session(db: Session, *, user: User, title: str, provider_config_id: UUID | None, library_id: UUID | None) -> ChatSession:
    if provider_config_id:
        provider = (
            db.query(ProviderConfig)
            .filter(ProviderConfig.id == provider_config_id, ProviderConfig.owner_id == user.id)
            .first()
        )
        if not provider:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Provider config not found')

    if library_id:
        library = db.query(KnowledgeLibrary).filter(KnowledgeLibrary.id == library_id).first()
        if not library:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Library not found')
        if library.owner_type == OwnerTypeEnum.private and library.owner_id != user.id and user.role != RoleEnum.admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='No access to this library')

    session = ChatSession(
        user_id=user.id,
        title=title,
        provider_config_id=provider_config_id,
        library_id=library_id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: Session, *, user: User) -> list[ChatSession]:
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )


def delete_session(db: Session, *, user: User, session_id: UUID) -> None:
    session = _get_session_or_404(db, session_id)
    if session.user_id != user.id and user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='No access to this session')
    # 删除会话相关的消息
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    # 删除会话
    db.delete(session)
    db.commit()


def list_messages(db: Session, *, user: User, session_id: UUID) -> list[ChatMessage]:
    session = _get_session_or_404(db, session_id)
    if session.user_id != user.id and user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='No access to this session')

    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )


def generate_reply(
    db: Session,
    *,
    user: User,
    session_id: UUID,
    content: str,
    provider_config_id: UUID | None,
    library_ids: list[UUID] | None,
    top_k: int,
    use_rerank: bool,
    show_citations: bool,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> tuple[str, list[dict]]:
    session = _get_session_or_404(db, session_id)
    if session.user_id != user.id and user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='No access to this session')

    user_message = ChatMessage(session_id=session.id, role=ChatRoleEnum.user, content=content, citations=[])
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    available_library_ids = _resolve_libraries(db, user, session.library_id, library_ids)
    retrieved = hybrid_search(db, library_ids=available_library_ids, query=content, top_k=top_k)

    if available_library_ids and not retrieved:
        no_hit_content = _build_no_hit_message()
        assistant_message = ChatMessage(
            session_id=session.id,
            role=ChatRoleEnum.assistant,
            content=no_hit_content,
            citations=[],
        )
        db.add(assistant_message)
        db.commit()
        return no_hit_content, []

    selected_provider = _resolve_provider(db, user, provider_config_id or session.provider_config_id)

    if use_rerank and retrieved:
        runtime = to_runtime_config(selected_provider)
        adapter = provider_registry.get(runtime['provider_type'])
        rerank = adapter.rerank(
            ProviderConfigDTO(**runtime),
            RerankRequest(
                model=runtime['model_name'],
                query=content,
                documents=[item['snippet'] for item in retrieved],
            ),
        )
        sorted_items = sorted(rerank.items, key=lambda item: item.score, reverse=True)
        reordered = []
        for item in sorted_items:
            if 0 <= item.index < len(retrieved):
                row = retrieved[item.index]
                row['score'] = float(item.score)
                reordered.append(row)
        if reordered:
            retrieved = reordered

    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    if retrieved:
        # 将UUID转换为字符串以便JSON序列化
        serializable_retrieved = []
        for item in retrieved:
            serialized = {}
            for k, v in item.items():
                if isinstance(v, UUID):
                    serialized[k] = str(v)
                else:
                    serialized[k] = v
            serializable_retrieved.append(serialized)
        system_content = (
            '你是企业知识助手。请优先使用知识库内容回答，并保持答案准确。'
            'RAG_CONTEXT=' + json.dumps(serializable_retrieved, ensure_ascii=False)
        )
    else:
        system_content = '你是企业知识助手。在未选择知识库时，可直接基于模型能力回答用户问题。'

    messages: list[dict[str, Any]] = [{'role': 'system', 'content': system_content}]
    for msg in history:
        messages.append({'role': msg.role.value, 'content': msg.content})

    runtime = to_runtime_config(selected_provider)
    adapter = provider_registry.get(runtime['provider_type'])

    response = adapter.chat(
        ProviderConfigDTO(**runtime),
        ChatRequest(
            model=runtime['model_name'],
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        ),
    )

    citations = []
    if show_citations:
        citations = [
            {
                'library_id': str(item['library_id']),
                'file_id': str(item['file_id']),
                'file_name': item['file_name'],
                'chunk_id': str(item['chunk_id']),
                'score': float(item['score']),
                'snippet': item['snippet'],
                'source': item['source'],
                'matched_entities': item.get('matched_entities', []),
            }
            for item in retrieved
        ]

    assistant_message = ChatMessage(
        session_id=session.id,
        role=ChatRoleEnum.assistant,
        content=response.content,
        citations=citations,
    )
    db.add(assistant_message)
    db.commit()

    return response.content, citations


def _get_session_or_404(db: Session, session_id: UUID) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Session not found')
    return session


def generate_reply_stream(
    db: Session,
    *,
    user: User,
    session_id: UUID,
    content: str,
    provider_config_id: UUID | None,
    library_ids: list[UUID] | None,
    top_k: int,
    use_rerank: bool,
    show_citations: bool,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> tuple[Iterator[str], list[dict]]:
    """流式生成回复，返回 (stream_iterator, citations)"""
    from app.services.providers.base import ChatDelta

    session = _get_session_or_404(db, session_id)
    if session.user_id != user.id and user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='No access to this session')

    # 获取历史消息（用于多轮对话上下文增强）
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    # 提取历史用户消息用于增强检索
    history_context = [msg.content for msg in history if msg.role == ChatRoleEnum.user]

    # 保存用户消息
    user_message = ChatMessage(session_id=session.id, role=ChatRoleEnum.user, content=content, citations=[])
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    # RAG 检索（传入历史上下文）
    available_library_ids = _resolve_libraries(db, user, session.library_id, library_ids)
    retrieved = hybrid_search(
        db,
        library_ids=available_library_ids,
        query=content,
        top_k=top_k,
        history_context=history_context,
    )

    if available_library_ids and not retrieved:
        no_hit_content = _build_no_hit_message()
        session_id_value = session.id

        def no_hit_stream() -> Iterator[str]:
            assistant_message = ChatMessage(
                session_id=session_id_value,
                role=ChatRoleEnum.assistant,
                content=no_hit_content,
                citations=[],
            )
            db.add(assistant_message)
            db.commit()
            yield f"data: {json.dumps({'type': 'delta', 'delta': no_hit_content}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'citations': []}, ensure_ascii=False)}\n\n"

        return no_hit_stream(), []

    selected_provider = _resolve_provider(db, user, provider_config_id or session.provider_config_id)

    # 重新排序
    if use_rerank and retrieved:
        runtime = to_runtime_config(selected_provider)
        adapter = provider_registry.get(runtime['provider_type'])
        rerank = adapter.rerank(
            ProviderConfigDTO(**runtime),
            RerankRequest(
                model=runtime['model_name'],
                query=content,
                documents=[item['snippet'] for item in retrieved],
            ),
        )
        sorted_items = sorted(rerank.items, key=lambda item: item.score, reverse=True)
        reordered = []
        for item in sorted_items:
            if 0 <= item.index < len(retrieved):
                row = retrieved[item.index]
                row['score'] = float(item.score)
                reordered.append(row)
        if reordered:
            retrieved = reordered

    # 构建 system prompt
    if retrieved:
        serializable_retrieved = []
        for item in retrieved:
            serialized = {}
            for k, v in item.items():
                if isinstance(v, UUID):
                    serialized[k] = str(v)
                else:
                    serialized[k] = v
            serializable_retrieved.append(serialized)
        system_content = (
            '你是企业知识助手。请根据知识库检索结果回答用户问题。\n'
            '要求：\n'
            '1. 如果检索结果与问题相关，请基于检索内容直接回答，不要解释检索过程\n'
            '2. 如果检索结果与问题无关或信息不足，请明确告知用户\n'
            '3. 回答要简洁准确，避免过度引申\n\n'
            '知识库检索结果：\n' + json.dumps(serializable_retrieved, ensure_ascii=False, indent=2)
        )
    else:
        system_content = '你是企业知识助手。在未选择知识库时，可直接基于模型能力回答用户问题。'

    # 构建消息列表（history 已在前面获取，不包含当前用户消息）
    messages: list[dict[str, Any]] = [{'role': 'system', 'content': system_content}]
    for msg in history:
        messages.append({'role': msg.role.value, 'content': msg.content})
    # 添加当前用户消息
    messages.append({'role': 'user', 'content': content})

    runtime = to_runtime_config(selected_provider)
    adapter = provider_registry.get(runtime['provider_type'])

    # 提前获取 session_id，避免在生成器中访问 detached session
    session_id_value = session.id

    # 流式调用 LLM
    def stream_generator() -> Iterator[str]:
        full_content = ''
        for delta in adapter.chat_stream(
            ProviderConfigDTO(**runtime),
            ChatRequest(
                model=runtime['model_name'],
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            ),
        ):
            if delta.delta:
                full_content += delta.delta
                chunk = {'type': 'delta', 'delta': delta.delta}
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        # 流式结束后保存消息到数据库
        citations = []
        if show_citations:
            citations = [
                {
                    'library_id': str(item['library_id']),
                    'file_id': str(item['file_id']),
                    'file_name': item['file_name'],
                    'chunk_id': str(item['chunk_id']),
                    'score': float(item['score']),
                    'snippet': item['snippet'],
                    'source': item['source'],
                    'matched_entities': item.get('matched_entities', []),
                }
                for item in retrieved
            ]

        assistant_message = ChatMessage(
            session_id=session_id_value,
            role=ChatRoleEnum.assistant,
            content=full_content,
            citations=citations,
        )
        db.add(assistant_message)
        db.commit()

        done = {'type': 'done', 'citations': citations}
        yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"

    return stream_generator(), []


def _resolve_provider(db: Session, user: User, provider_config_id: UUID | None) -> ProviderConfig:
    query = db.query(ProviderConfig).filter(ProviderConfig.owner_id == user.id)

    if provider_config_id:
        provider = query.filter(ProviderConfig.id == provider_config_id).first()
        if not provider:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Provider config not found')
        return provider

    provider = query.filter(ProviderConfig.is_default.is_(True)).first() or query.first()
    if not provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='No provider configured')
    return provider


def _resolve_libraries(
    db: Session,
    user: User,
    session_library_id: UUID | None,
    request_library_ids: list[UUID] | None,
) -> list[UUID]:
    library_ids = request_library_ids or ([] if session_library_id is None else [session_library_id])
    if not library_ids:
        return []

    libraries = db.query(KnowledgeLibrary).filter(KnowledgeLibrary.id.in_(library_ids)).all()
    available = []
    for library in libraries:
        if library.owner_type == OwnerTypeEnum.shared:
            available.append(library.id)
            continue
        if library.owner_id == user.id or user.role == RoleEnum.admin:
            available.append(library.id)
    return available


def _build_no_hit_message() -> str:
    return (
        '当前问题未命中所选知识库内容，已停止使用通用大模型兜底回答。\n'
        '建议操作：\n'
        '1. 使用别名/简称重试（例如：猪八戒、八戒、悟能）\n'
        '2. 在知识库页面执行“重建索引”和“重建图谱”\n'
        '3. 确认相关文档已上传到当前会话选择的知识库'
    )
