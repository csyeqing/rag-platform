from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.chat import (
    ChatMessageCreateRequest,
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatSessionCreateRequest,
    ChatSessionResponse,
    ChatSessionUpdateRequest,
)
from app.services.retrieval_profile_service import get_profile_config_by_id
from app.services.chat_service import create_session, delete_session, generate_reply, generate_reply_stream, list_messages, list_sessions
from app.utils.audit import write_audit_log

router = APIRouter(prefix='/chat', tags=['chat'])


@router.post('/sessions', response_model=ChatSessionResponse)
def create_session_endpoint(
    payload: ChatSessionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    session = create_session(
        db,
        user=current_user,
        title=payload.title,
        provider_config_id=payload.provider_config_id,
        library_id=payload.library_id,
        retrieval_profile_id=payload.retrieval_profile_id,
    )
    write_audit_log(
        db,
        action='chat.session.create',
        resource_type='chat_session',
        resource_id=str(session.id),
        user_id=current_user.id,
    )
    return _to_session_response(session)


@router.get('/sessions', response_model=list[ChatSessionResponse])
def list_sessions_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatSessionResponse]:
    sessions = list_sessions(db, user=current_user)
    return [_to_session_response(item) for item in sessions]


@router.delete('/sessions/{session_id}')
def delete_session_endpoint(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    delete_session(db, user=current_user, session_id=session_id)


@router.patch('/sessions/{session_id}', response_model=ChatSessionResponse)
def update_session_endpoint(
    session_id: UUID,
    payload: ChatSessionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    from app.db.models import ChatSession
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id).first()
    if not session:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Session not found')
    incoming = payload.model_dump(exclude_unset=True)
    if 'title' in incoming:
        session.title = payload.title
    if 'provider_config_id' in incoming:
        session.provider_config_id = payload.provider_config_id
    if 'library_id' in incoming:
        session.library_id = payload.library_id
    if 'retrieval_profile_id' in incoming:
        resolved_profile_id, _ = get_profile_config_by_id(db, payload.retrieval_profile_id)
        session.retrieval_profile_id = resolved_profile_id
    if 'show_citations' in incoming:
        session.show_citations = payload.show_citations
    db.commit()
    db.refresh(session)
    return _to_session_response(session)


@router.post('/sessions/{session_id}/messages')
def create_message_endpoint(
    session_id: UUID,
    payload: ChatMessageCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.stream:
        # 真流式响应
        stream_generator, _ = generate_reply_stream(
            db,
            user=current_user,
            session_id=session_id,
            content=payload.content,
            provider_config_id=payload.provider_config_id,
            library_ids=payload.library_ids,
            retrieval_profile_id=payload.retrieval_profile_id,
            top_k=payload.top_k,
            use_rerank=payload.use_rerank,
            show_citations=payload.show_citations,
            temperature=payload.temperature,
            top_p=payload.top_p,
            max_tokens=payload.max_tokens,
        )

        write_audit_log(
            db,
            action='chat.message.create',
            resource_type='chat_session',
            resource_id=str(session_id),
            user_id=current_user.id,
            metadata={'stream': True},
        )

        return StreamingResponse(
            stream_generator,
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'},
        )

    # 非流式响应
    content, citations = generate_reply(
        db,
        user=current_user,
        session_id=session_id,
        content=payload.content,
        provider_config_id=payload.provider_config_id,
        library_ids=payload.library_ids,
        retrieval_profile_id=payload.retrieval_profile_id,
        top_k=payload.top_k,
        use_rerank=payload.use_rerank,
        show_citations=payload.show_citations,
        temperature=payload.temperature,
        top_p=payload.top_p,
        max_tokens=payload.max_tokens,
    )

    write_audit_log(
        db,
        action='chat.message.create',
        resource_type='chat_session',
        resource_id=str(session_id),
        user_id=current_user.id,
        metadata={'stream': False, 'citations': len(citations)},
    )

    return {'content': content, 'citations': citations}


@router.get('/sessions/{session_id}/messages', response_model=ChatMessageListResponse)
def list_messages_endpoint(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessageListResponse:
    messages = list_messages(db, user=current_user, session_id=session_id)
    return ChatMessageListResponse(items=[_to_message_response(item) for item in messages])


def _to_session_response(session) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        provider_config_id=session.provider_config_id,
        library_id=session.library_id,
        retrieval_profile_id=session.retrieval_profile_id,
        show_citations=session.show_citations,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _to_message_response(msg) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role.value,
        content=msg.content,
        citations=msg.citations,
        created_at=msg.created_at,
    )
