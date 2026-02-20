from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import KnowledgeFile, User
from app.db.session import get_db
from app.schemas.kb import (
    IngestionTaskResponse,
    KnowledgeFileResponse,
    KnowledgeGraphRebuildResponse,
    KnowledgeGraphResponse,
    KnowledgeLibraryCreateRequest,
    KnowledgeLibraryUpdateRequest,
    KnowledgeLibraryResponse,
    RebuildIndexRequest,
    SyncDirectoryRequest,
)
from app.services.kb_service import (
    assert_library_access,
    create_library,
    delete_knowledge_file,
    delete_library,
    get_file_or_404,
    get_ingestion_task,
    get_library_graph,
    get_library_or_404,
    list_library_files,
    list_libraries,
    rebuild_library_graph_index,
    rebuild_index,
    save_uploaded_file,
    sync_directory,
    update_library,
)
from app.utils.audit import write_audit_log

router = APIRouter(prefix='/kb', tags=['knowledge-base'])


@router.post('/libraries', response_model=KnowledgeLibraryResponse)
def create_library_endpoint(
    payload: KnowledgeLibraryCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeLibraryResponse:
    library = create_library(
        db,
        current_user,
        name=payload.name,
        description=payload.description,
        library_type=payload.library_type,
        owner_type=payload.owner_type,
        tags=payload.tags,
        root_path=payload.root_path,
    )
    write_audit_log(
        db,
        action='kb.library.create',
        resource_type='knowledge_library',
        resource_id=str(library.id),
        user_id=current_user.id,
        metadata={'owner_type': library.owner_type.value, 'library_type': library.library_type},
    )
    return _to_library_response(library)


@router.get('/libraries', response_model=list[KnowledgeLibraryResponse])
def list_libraries_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[KnowledgeLibraryResponse]:
    rows = list_libraries(db, current_user)
    return [_to_library_response(item) for item in rows]


@router.put('/libraries/{library_id}', response_model=KnowledgeLibraryResponse)
def update_library_endpoint(
    library_id: UUID,
    payload: KnowledgeLibraryUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeLibraryResponse:
    library = get_library_or_404(db, library_id)
    updated = update_library(
        db,
        library=library,
        user=current_user,
        name=payload.name,
        description=payload.description,
        library_type=payload.library_type,
        owner_type=payload.owner_type,
        tags=payload.tags,
    )
    write_audit_log(
        db,
        action='kb.library.update',
        resource_type='knowledge_library',
        resource_id=str(updated.id),
        user_id=current_user.id,
        metadata={'owner_type': updated.owner_type.value, 'library_type': updated.library_type, 'tags': updated.tags},
    )
    return _to_library_response(updated)


@router.delete('/libraries/{library_id}')
def delete_library_endpoint(
    library_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    library = get_library_or_404(db, library_id)
    delete_library(db, library=library, user=current_user)
    write_audit_log(
        db,
        action='kb.library.delete',
        resource_type='knowledge_library',
        resource_id=str(library_id),
        user_id=current_user.id,
    )
    return {'message': 'deleted'}


@router.post('/files/upload', response_model=KnowledgeFileResponse)
def upload_file_endpoint(
    library_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeFileResponse:
    library = get_library_or_404(db, library_id)
    assert_library_access(library, current_user, write=True)

    knowledge_file = save_uploaded_file(db, library=library, uploaded_file=file)
    write_audit_log(
        db,
        action='kb.file.upload',
        resource_type='knowledge_file',
        resource_id=str(knowledge_file.id),
        user_id=current_user.id,
        metadata={'library_id': str(library.id), 'filename': knowledge_file.filename},
    )

    return _to_file_response(knowledge_file)


@router.get('/libraries/{library_id}/files', response_model=list[KnowledgeFileResponse])
def list_library_files_endpoint(
    library_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[KnowledgeFileResponse]:
    library = get_library_or_404(db, library_id)
    rows = list_library_files(db, library=library, user=current_user)
    return [_to_file_response(item) for item in rows]


@router.delete('/files/{file_id}')
def delete_file_endpoint(
    file_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    knowledge_file = get_file_or_404(db, file_id)
    delete_knowledge_file(db, knowledge_file=knowledge_file, user=current_user)
    write_audit_log(
        db,
        action='kb.file.delete',
        resource_type='knowledge_file',
        resource_id=str(file_id),
        user_id=current_user.id,
    )
    return {'message': 'deleted'}


@router.get('/libraries/{library_id}/graph', response_model=KnowledgeGraphResponse)
def get_library_graph_endpoint(
    library_id: UUID,
    limit_nodes: int = 80,
    limit_edges: int = 150,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeGraphResponse:
    library = get_library_or_404(db, library_id)
    assert_library_access(library, current_user, write=False)
    snapshot = get_library_graph(
        db,
        library=library,
        limit_nodes=limit_nodes,
        limit_edges=limit_edges,
    )
    return KnowledgeGraphResponse(**snapshot)


@router.post('/libraries/{library_id}/graph/rebuild', response_model=KnowledgeGraphRebuildResponse)
def rebuild_library_graph_endpoint(
    library_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeGraphRebuildResponse:
    library = get_library_or_404(db, library_id)
    assert_library_access(library, current_user, write=True)

    stats = rebuild_library_graph_index(db, library=library)
    write_audit_log(
        db,
        action='kb.graph.rebuild',
        resource_type='knowledge_library',
        resource_id=str(library.id),
        user_id=current_user.id,
        metadata={'node_count': stats.get('node_count', 0), 'edge_count': stats.get('edge_count', 0)},
    )
    return KnowledgeGraphRebuildResponse(
        library_id=library.id,
        node_count=int(stats.get('node_count', 0)),
        edge_count=int(stats.get('edge_count', 0)),
        chunk_count=int(stats.get('chunk_count', 0)),
        message='知识图谱重建完成',
    )


@router.post('/files/sync-directory', response_model=IngestionTaskResponse)
def sync_directory_endpoint(
    payload: SyncDirectoryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestionTaskResponse:
    library = get_library_or_404(db, payload.library_id)
    assert_library_access(library, current_user, write=True)

    task = sync_directory(
        db,
        library=library,
        directory_path=payload.directory_path,
        recursive=payload.recursive,
        triggered_by=current_user,
    )
    write_audit_log(
        db,
        action='kb.sync_directory',
        resource_type='ingestion_task',
        resource_id=str(task.id),
        user_id=current_user.id,
        metadata={'library_id': str(library.id), 'directory_path': payload.directory_path},
    )

    return _to_task_response(task)


@router.post('/index/rebuild', response_model=IngestionTaskResponse)
def rebuild_index_endpoint(
    payload: RebuildIndexRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestionTaskResponse:
    library = get_library_or_404(db, payload.library_id)
    assert_library_access(library, current_user, write=True)

    task = rebuild_index(db, library=library, triggered_by=current_user)
    write_audit_log(
        db,
        action='kb.rebuild_index',
        resource_type='ingestion_task',
        resource_id=str(task.id),
        user_id=current_user.id,
        metadata={'library_id': str(library.id)},
    )

    return _to_task_response(task)


@router.get('/tasks/{task_id}', response_model=IngestionTaskResponse)
def get_task_endpoint(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestionTaskResponse:
    task = get_ingestion_task(db, task_id)
    library = get_library_or_404(db, task.library_id)
    assert_library_access(library, current_user, write=False)
    return _to_task_response(task)


def _to_library_response(library) -> KnowledgeLibraryResponse:
    return KnowledgeLibraryResponse(
        id=library.id,
        name=library.name,
        description=library.description,
        library_type=library.library_type,
        owner_type=library.owner_type.value,
        owner_id=library.owner_id,
        tags=library.tags,
        root_path=library.root_path,
        created_at=library.created_at,
        updated_at=library.updated_at,
    )


def _to_file_response(knowledge_file: KnowledgeFile) -> KnowledgeFileResponse:
    return KnowledgeFileResponse(
        id=knowledge_file.id,
        library_id=knowledge_file.library_id,
        filename=knowledge_file.filename,
        filepath=knowledge_file.filepath,
        file_type=knowledge_file.file_type,
        status=knowledge_file.status,
        created_at=knowledge_file.created_at,
        updated_at=knowledge_file.updated_at,
    )


def _to_task_response(task) -> IngestionTaskResponse:
    return IngestionTaskResponse(
        id=task.id,
        task_type=task.task_type.value,
        status=task.status.value,
        library_id=task.library_id,
        detail=task.detail,
        error_message=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )
