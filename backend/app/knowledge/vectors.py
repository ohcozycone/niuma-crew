"""Atomic vector snapshots and bounded exact cosine search for small libraries."""

from __future__ import annotations

import heapq
import math
import time
from threading import BoundedSemaphore
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.errors import ConflictError, InvalidInputError, ServiceUnavailableError
from app.infrastructure.database.fields import new_uuid, utc_now
from app.infrastructure.database.transactions import reserve_writer
from app.knowledge.contracts import Chunk, digest
from app.knowledge.models import (
    KnowledgeBase,
    LibraryChunk,
    LibraryDocument,
    LibraryVector,
    LibraryVectorIndex,
)
from app.knowledge.schemas import (
    EmbeddingConnectionRead,
    LibraryRead,
    SearchHit,
    SearchRequest,
    SearchResult,
)
from app.llm.embeddings import embed_texts
from app.model_connections.models import ModelConnection
from app.model_connections.service import ModelConnectionService

if TYPE_CHECKING:
    from app.knowledge.service import KnowledgeService


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
    connection = session.get(ModelConnection, index.connection_id)
    status = "ready"
    vector_count = (
        session.scalar(
            select(func.count())
            .select_from(LibraryVector)
            .where(LibraryVector.knowledge_base_id == kb)
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


class KnowledgeVectorService:
    def __init__(self, knowledge: KnowledgeService, connections: ModelConnectionService):
        self.knowledge, self.connections = knowledge, connections
        # One build per application process bounds CPU/memory and duplicate upstream charges.
        self.build_slot = BoundedSemaphore(1)

    def options(self, actor: Actor) -> list[EmbeddingConnectionRead]:
        self.knowledge.owner(actor)
        with self.knowledge.database.transaction() as session:
            return [
                EmbeddingConnectionRead(id=row.id, name=row.name, model_id=row.model_id)
                for row in session.scalars(
                    select(ModelConnection)
                    .where(
                        ModelConnection.enabled.is_(True), ModelConnection.capability == "embedding"
                    )
                    .order_by(ModelConnection.name, ModelConnection.id)
                )
            ]

    def build(self, actor: Actor, kb: str, connection_id: str) -> LibraryRead:
        self.knowledge.get(actor, kb)
        if not self.build_slot.acquire(blocking=False):
            raise ConflictError("knowledge_build_busy", "正在建立向量索引，请稍后重试。")
        try:
            return self._build(actor, kb, connection_id)
        finally:
            self.build_slot.release()

    def _build(self, actor: Actor, kb: str, connection_id: str) -> LibraryRead:
        deadline = time.monotonic() + 120
        with self.knowledge.database.transaction() as session:
            base_revision = self.knowledge.require_base(session, kb, actor).updated_at
            config = self.connections.resolve_embedding(connection_id, db=session)
            old = session.get(LibraryVectorIndex, kb)
            generation = old.generation if old else None
            source = source_digest(session, kb)
            chunks = [
                Chunk.model_validate(row.snapshot)
                for row in session.scalars(
                    select(LibraryChunk)
                    .join(LibraryDocument)
                    .where(LibraryDocument.knowledge_base_id == kb)
                    .order_by(LibraryChunk.id)
                )
            ]
        if not chunks:
            raise InvalidInputError(
                "knowledge_empty", "请先处理文档生成关键词索引，再建立向量索引。"
            )

        def guard() -> None:
            if time.monotonic() > deadline:
                raise ServiceUnavailableError(
                    "knowledge_build_timeout", "向量构建超时，原索引保留，请稍后重试。"
                )
            self.connections.resolve_embedding(
                connection_id, config.config_revision, config.credential_revision
            )

        vectors = embed_texts(config, [chunk.text for chunk in chunks], guard)
        with self.knowledge.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            base = self.knowledge.require_base(session, kb, actor)
            self.connections.resolve_embedding(
                connection_id, config.config_revision, config.credential_revision, db=session
            )
            current = session.get(LibraryVectorIndex, kb)
            if (
                base.updated_at != base_revision
                or source_digest(session, kb) != source
                or (current.generation if current else None) != generation
            ):
                raise ConflictError(
                    "knowledge_build_changed", "构建期间资料或索引已变化，请重新建立索引。"
                )
            session.execute(delete(LibraryVector).where(LibraryVector.knowledge_base_id == kb))
            if current is None:
                current = LibraryVectorIndex(knowledge_base_id=kb)
                session.add(current)
            current.connection_id = connection_id
            current.config_revision = config.config_revision
            current.source_digest = source
            current.chunk_count = len(chunks)
            current.generation = new_uuid()
            session.add_all(
                [
                    LibraryVector(chunk_id=chunk.id, knowledge_base_id=kb, vector=vector)
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ]
            )
            session.flush()
            return self.knowledge.base_read(session, base)

    def clear(self, actor: Actor, kb: str) -> None:
        with self.knowledge.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            self.knowledge.require_base(session, kb, actor).updated_at = utc_now()
            session.execute(delete(LibraryVector).where(LibraryVector.knowledge_base_id == kb))
            session.execute(
                delete(LibraryVectorIndex).where(LibraryVectorIndex.knowledge_base_id == kb)
            )

    def search(self, actor: Actor, kb: str, data: SearchRequest) -> SearchResult:
        with self.knowledge.database.transaction() as session:
            status = self.knowledge.base_read(
                session, self.knowledge.require_base(session, kb, actor)
            )
            if status.vector_status not in {"ready", "partial"}:
                raise ConflictError(
                    "knowledge_vector_not_ready",
                    "向量索引尚未建立、已过期或连接已停用，请先检查并重建索引。",
                )
            index = session.get(LibraryVectorIndex, kb)
            assert index is not None
            generation = index.generation
            source = source_digest(session, kb)
            config = self.connections.resolve_embedding(
                index.connection_id, index.config_revision, db=session
            )
        query = embed_texts(config, [data.question])[0]
        with self.knowledge.database.transaction() as session:
            base = self.knowledge.require_base(session, kb, actor)
            current = session.get(LibraryVectorIndex, kb)
            if (
                current is None
                or current.generation != generation
                or source_digest(session, kb) != source
                or self.knowledge.base_read(session, base).vector_status not in {"ready", "partial"}
            ):
                raise ConflictError(
                    "knowledge_index_changed", "检索期间索引或资料已变化，请重新检索。"
                )
            self.connections.resolve_embedding(
                config.connection_id, config.config_revision, config.credential_revision, db=session
            )
            rows = session.execute(
                select(LibraryVector.vector, LibraryChunk.snapshot)
                .join(LibraryChunk, LibraryChunk.id == LibraryVector.chunk_id)
                .join(LibraryDocument, LibraryDocument.id == LibraryChunk.document_id)
                .where(
                    LibraryVector.knowledge_base_id == kb, LibraryDocument.knowledge_base_id == kb
                )
                .execution_options(yield_per=32)
            )
            scored = (
                (
                    max(
                        -1.0,
                        min(
                            1.0,
                            math.fsum(
                                a * b for a, b in zip(query, cast(list[float], vector), strict=True)
                            ),
                        ),
                    ),
                    Chunk.model_validate(snapshot),
                )
                for vector, snapshot in rows
            )
            limit = 30 if data.strategy == "hybrid" else data.top_k
            best = heapq.nsmallest(limit, scored, key=lambda item: (-item[0], item[1].id))
            hits = [
                SearchHit(rank=i, score=score, score_kind="cosine_higher_better", chunk=chunk)
                for i, (score, chunk) in enumerate(best, 1)
            ]
            if data.strategy == "hybrid":
                lexical = self.knowledge.lexical_search(session, kb, data.question, limit)
                hits = reciprocal_rank_fusion(lexical, hits, data.top_k)
            return SearchResult(
                knowledge_base_id=kb,
                strategy=data.strategy,
                hits=hits,
            )


def reciprocal_rank_fusion(
    lexical: list[SearchHit], semantic: list[SearchHit], top_k: int
) -> list[SearchHit]:
    """Fuse ranks, since BM25 and cosine scores have different scales."""
    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}
    for candidates in (lexical, semantic):
        for rank, hit in enumerate(candidates, 1):
            id = hit.chunk.id
            scores[id] = scores.get(id, 0.0) + 1 / (60 + rank)
            chunks[id] = hit.chunk
    ordered = sorted(scores, key=lambda id: (-scores[id], id))[:top_k]
    return [
        SearchHit(rank=rank, score=scores[id], score_kind="rrf_higher_better", chunk=chunks[id])
        for rank, id in enumerate(ordered, 1)
    ]
