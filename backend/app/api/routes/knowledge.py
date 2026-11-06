"""Library administration, bounded raw-byte upload and scope-bound BM25 preview."""

import asyncio
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import Response

from app.api.dependencies import ActorDependency, KnowledgeDependency, LimiterDependency
from app.errors import InvalidInputError
from app.knowledge.schemas import (
    ChunkPreviewRead,
    ChunkPreviewRequest,
    CitationPreviewRead,
    DemoImport,
    DocumentDetail,
    DocumentRead,
    EmbeddingConnectionRead,
    EmployeeKnowledgeInput,
    EmployeeKnowledgeRead,
    LibraryCreate,
    LibraryRead,
    LibraryUpdate,
    ProcessingBatchRead,
    ProcessingRequest,
    SearchRequest,
    SearchResult,
    VectorBuild,
)
from app.knowledge.service import MAX_DOCUMENT_BYTES

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge"])


@router.get("/employee-bindings/{agent_id}", response_model=EmployeeKnowledgeRead)
def get_employee_bindings(agent_id: UUID, actor: ActorDependency, knowledge: KnowledgeDependency):
    return knowledge.assignments.get(actor, str(agent_id))


@router.put("/employee-bindings/{agent_id}", response_model=EmployeeKnowledgeRead)
def replace_employee_bindings(
    agent_id: UUID,
    data: EmployeeKnowledgeInput,
    actor: ActorDependency,
    knowledge: KnowledgeDependency,
):
    return knowledge.assignments.replace(actor, str(agent_id), data)


@router.get("/embedding-connections", response_model=list[EmbeddingConnectionRead])
def embedding_connections(actor: ActorDependency, knowledge: KnowledgeDependency):
    return knowledge.vectors.options(actor)


@router.post("/{kb_id}/vector-index", response_model=LibraryRead)
def build_vector_index(
    kb_id: UUID,
    data: VectorBuild,
    actor: ActorDependency,
    knowledge: KnowledgeDependency,
    limiter: LimiterDependency,
):
    limiter.consume(f"knowledge-vector-build:{actor.user_id}", 3, 60)
    return knowledge.vectors.build(actor, str(kb_id), str(data.model_connection_id))


@router.delete("/{kb_id}/vector-index", status_code=204, response_class=Response)
def clear_vector_index(kb_id: UUID, actor: ActorDependency, knowledge: KnowledgeDependency):
    knowledge.vectors.clear(actor, str(kb_id))


@router.get("", response_model=list[LibraryRead])
def list_libraries(actor: ActorDependency, knowledge: KnowledgeDependency):
    return knowledge.libraries(actor)


@router.post("", status_code=201, response_model=LibraryRead)
def create_library(data: LibraryCreate, actor: ActorDependency, knowledge: KnowledgeDependency):
    return knowledge.create(actor, data)


@router.get("/{kb_id}", response_model=LibraryRead)
def get_library(kb_id: UUID, actor: ActorDependency, knowledge: KnowledgeDependency):
    return knowledge.get(actor, str(kb_id))


@router.patch("/{kb_id}", response_model=LibraryRead)
def update_library(
    kb_id: UUID, data: LibraryUpdate, actor: ActorDependency, knowledge: KnowledgeDependency
):
    return knowledge.update(actor, str(kb_id), data)


@router.post("/{kb_id}/processing", status_code=202, response_model=ProcessingBatchRead)
def process_documents(
    kb_id: UUID,
    data: ProcessingRequest,
    actor: ActorDependency,
    knowledge: KnowledgeDependency,
    limiter: LimiterDependency,
):
    limiter.consume(f"knowledge-process:{actor.user_id}", 20, 60)
    return knowledge.processing.submit(actor, str(kb_id), data)


@router.get("/{kb_id}/processing", response_model=list[ProcessingBatchRead])
def list_processing(kb_id: UUID, actor: ActorDependency, knowledge: KnowledgeDependency):
    return knowledge.processing.batches(actor, str(kb_id))


@router.get("/{kb_id}/processing/{batch_id}", response_model=ProcessingBatchRead)
def get_processing(
    kb_id: UUID, batch_id: UUID, actor: ActorDependency, knowledge: KnowledgeDependency
):
    return knowledge.processing.get(actor, str(kb_id), str(batch_id))


@router.post("/{kb_id}/processing/{batch_id}/cancel", response_model=ProcessingBatchRead)
def cancel_processing(
    kb_id: UUID, batch_id: UUID, actor: ActorDependency, knowledge: KnowledgeDependency
):
    return knowledge.processing.cancel(actor, str(kb_id), str(batch_id))


@router.get("/{kb_id}/documents", response_model=list[DocumentRead])
def list_documents(kb_id: UUID, actor: ActorDependency, knowledge: KnowledgeDependency):
    return knowledge.documents(actor, str(kb_id))


@router.post("/{kb_id}/documents", status_code=201, response_model=DocumentRead)
async def upload_document(
    request: Request,
    kb_id: UUID,
    actor: ActorDependency,
    knowledge: KnowledgeDependency,
    limiter: LimiterDependency,
    name: str = Query(min_length=1, max_length=255),
    client_request_id: UUID = Query(),
):
    # Check ownership before buffering/parsing. DB access is moved off the event loop.
    await asyncio.to_thread(knowledge.get, actor, str(kb_id))
    limiter.consume(f"knowledge-upload:{actor.user_id}", 30, 60)
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_DOCUMENT_BYTES:
            raise InvalidInputError("knowledge_file_too_large", "单份知识文档不能超过 128 KiB。")
        content.extend(chunk)
    return await asyncio.to_thread(
        knowledge.upload, actor, str(kb_id), str(client_request_id), name, bytes(content)
    )


@router.get("/{kb_id}/documents/{document_id}", response_model=DocumentDetail)
def get_document(
    kb_id: UUID, document_id: UUID, actor: ActorDependency, knowledge: KnowledgeDependency
):
    return knowledge.detail(actor, str(kb_id), str(document_id))


@router.get(
    "/{kb_id}/documents/{document_id}/chunks/{chunk_id}", response_model=CitationPreviewRead
)
def citation_preview(
    kb_id: UUID,
    document_id: UUID,
    chunk_id: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
    actor: ActorDependency,
    knowledge: KnowledgeDependency,
):
    return knowledge.citation_preview(actor, str(kb_id), str(document_id), chunk_id)


@router.post("/{kb_id}/documents/{document_id}/preview", response_model=ChunkPreviewRead)
def preview_document(
    kb_id: UUID,
    document_id: UUID,
    data: ChunkPreviewRequest,
    actor: ActorDependency,
    knowledge: KnowledgeDependency,
    limiter: LimiterDependency,
):
    limiter.consume(f"knowledge-preview:{actor.user_id}", 30, 60)
    return knowledge.processing.preview(actor, str(kb_id), str(document_id), data)


@router.delete("/{kb_id}/documents/{document_id}", status_code=204)
def remove_document(
    kb_id: UUID, document_id: UUID, actor: ActorDependency, knowledge: KnowledgeDependency
):
    knowledge.remove(actor, str(kb_id), str(document_id))


@router.get("/{kb_id}/documents/{document_id}/original", response_class=Response)
def download(
    kb_id: UUID, document_id: UUID, actor: ActorDependency, knowledge: KnowledgeDependency
):
    name, content = knowledge.download(actor, str(kb_id), str(document_id))
    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name, safe=""),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{kb_id}/search", response_model=SearchResult)
def search(
    kb_id: UUID,
    data: SearchRequest,
    actor: ActorDependency,
    knowledge: KnowledgeDependency,
    limiter: LimiterDependency,
):
    if data.strategy in {"vector", "hybrid"}:
        limiter.consume(f"knowledge-vector-search:{actor.user_id}", 30, 60)
    return knowledge.search(actor, str(kb_id), data)


@router.post("/{kb_id}/demo-import", response_model=list[DocumentRead])
def import_demo(
    kb_id: UUID,
    data: DemoImport,
    actor: ActorDependency,
    knowledge: KnowledgeDependency,
    limiter: LimiterDependency,
):
    limiter.consume(f"knowledge-demo:{actor.user_id}", 6, 60)
    return knowledge.import_demo(actor, str(kb_id), data.preset, str(data.client_request_id))
