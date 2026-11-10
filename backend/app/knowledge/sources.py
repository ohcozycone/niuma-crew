from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ConflictError
from app.knowledge.contracts import EvidenceSource
from app.knowledge.models import (
    LibraryChunk,
    LibraryDocument,
    LibraryVectorIndex,
    LibraryVectorMembership,
)
from app.model_connections.references import connection_fact
from app.values import digest


def source_digest(session: Session, kb: str) -> str:
    return digest(
        list(
            session.scalars(
                select(LibraryChunk.id)
                .join(LibraryDocument)
                .where(LibraryDocument.knowledge_base_id == kb)
                .order_by(LibraryChunk.id)
            )
        )
    )


def index_summary(session: Session, kb: str, chunk_count: int) -> dict[str, Any]:
    index = session.get(LibraryVectorIndex, kb)
    if index is None:
        return {}
    connection = connection_fact(session, index.connection_id)
    status = "ready"
    vector_count = (
        session.scalar(
            select(func.count())
            .select_from(LibraryVectorMembership)
            .where(
                LibraryVectorMembership.knowledge_base_id == kb,
                LibraryVectorMembership.generation == index.generation,
            )
        )
        or 0
    )
    if connection is None or not connection.enabled or connection.capability != "embedding":
        status = "unavailable"
    elif connection.config_revision != index.config_revision:
        status = "outdated"
    elif vector_count == 0:
        status = "not_built"
    elif vector_count < chunk_count:
        status = "partial"
    return {
        "vector_status": status,
        "vector_connection_id": index.connection_id,
        "vector_connection_name": connection.name if connection else None,
        "vector_chunk_count": vector_count,
    }


def context_revision(db: Session, captured: dict) -> str:
    """知识依据改变时使旧执行记忆失效。"""
    ids = [item["id"] for item in captured["libraries"]]
    versions = list(
        db.execute(
            select(LibraryDocument.id, LibraryDocument.updated_at, LibraryDocument.content_hash)
            .where(LibraryDocument.knowledge_base_id.in_(ids))
            .order_by(LibraryDocument.id)
        )
    )
    return digest([captured["revision"], ids, [[str(value) for value in row] for row in versions]])


def assert_evidence(db: Session, evidence: EvidenceSource, ids: set[str]) -> None:
    document = db.get(LibraryDocument, evidence.document_id)
    chunk = db.get(LibraryChunk, evidence.chunk_id)
    if (
        evidence.knowledge_base_id not in ids
        or document is None
        or chunk is None
        or document.knowledge_base_id != evidence.knowledge_base_id
        or document.snapshot.get("version") != evidence.document_version
        or chunk.document_id != document.id
        or chunk.snapshot != evidence.snapshot
    ):
        raise ConflictError(
            "knowledge_source_changed", "已取得的知识来源已删除或重处理，请重新提问。"
        )
