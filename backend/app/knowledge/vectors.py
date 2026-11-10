from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from threading import BoundedSemaphore

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.errors import ConflictError, InvalidInputError, ServiceUnavailableError
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.knowledge.contracts import Chunk
from app.knowledge.lexical import lexical_search
from app.knowledge.libraries import KnowledgeLibraries
from app.knowledge.models import (
    KnowledgeBase,
    LibraryChunk,
    LibraryDocument,
    LibraryVectorIndex,
    LibraryVectorMembership,
)
from app.knowledge.retrieval import fuse_rankings
from app.knowledge.schemas import (
    EmbeddingConnectionRead,
    LibraryRead,
    SearchHit,
    SearchRequest,
    SearchResult,
)
from app.knowledge.sources import source_digest
from app.knowledge.vector_store import PREFIX, KnowledgeVectorStore
from app.llm.embeddings import VECTOR_DIMENSIONS, embed_texts
from app.model_connections.references import embedding_connections
from app.model_connections.service import ModelConnectionService
from app.values import digest, new_uuid, utc_now

logger = logging.getLogger(__name__)


class KnowledgeVectorService:
    def __init__(
        self,
        database: Database,
        libraries: KnowledgeLibraries,
        connections: ModelConnectionService,
        directory: Path,
    ) -> None:
        self.database, self.libraries, self.connections = database, libraries, connections
        self.store = KnowledgeVectorStore(directory)
        # 每进程只构建一项，限制资源及重复向量请求费用。
        self.build_slot = BoundedSemaphore(1)

    def options(self, actor: Actor) -> list[EmbeddingConnectionRead]:
        if actor.kind == "guest":
            require_permission(actor, "knowledge:read")
        else:
            self.libraries.manager(actor)
        with self.database.transaction() as session:
            return [
                EmbeddingConnectionRead(id=row.id, name=row.name, model_id=row.model_id)
                for row in embedding_connections(session)
            ]

    def build(self, actor: Actor, kb: str, connection_id: str) -> LibraryRead:
        self.libraries.manager(actor)
        self.libraries.get(actor, kb)
        if not self.build_slot.acquire(blocking=False):
            raise ConflictError("knowledge_build_busy", "正在建立向量索引，请稍后重试。")
        try:
            self.store.client  # 发起计费请求前先排除另一构建进程。
            return self._build(actor, kb, connection_id)
        finally:
            self.build_slot.release()

    def _build(self, actor: Actor, kb: str, connection_id: str) -> LibraryRead:
        deadline = time.monotonic() + 120
        with self.database.transaction() as session:
            base_revision = self.libraries.require_base(session, kb, actor).updated_at
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
        new_generation = new_uuid()
        name = PREFIX + digest([kb, new_generation])[:48]
        published = False
        old_name = None
        with self.store.use(name):
            try:
                self.store.build(name, chunks, vectors)
                guard()
                # 仅在获取或退役索引指针时持锁，网络请求和索引构建不占用 SQLite 写锁。
                with self.store.lock, self.database.transaction() as session:
                    reserve_writer(session, KnowledgeBase.__table__)
                    base = self.libraries.require_base(session, kb, actor)
                    self.connections.resolve_embedding(
                        connection_id,
                        config.config_revision,
                        config.credential_revision,
                        db=session,
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
                    old_name = current.collection_name if current else None
                    session.execute(
                        delete(LibraryVectorMembership).where(
                            LibraryVectorMembership.knowledge_base_id == kb
                        )
                    )
                    if current is None:
                        current = LibraryVectorIndex(knowledge_base_id=kb)
                        session.add(current)
                    current.connection_id = connection_id
                    current.config_revision = config.config_revision
                    current.source_digest = source
                    current.chunk_count = len(chunks)
                    current.generation = new_generation
                    current.collection_name = name
                    current.embedding_fingerprint = digest(
                        [config.base_url, config.model_id, VECTOR_DIMENSIONS, "cosine"]
                    )
                    session.add_all(
                        [
                            LibraryVectorMembership(
                                chunk_id=chunk.id,
                                knowledge_base_id=kb,
                                generation=new_generation,
                                document_id=chunk.document_id,
                                document_version=chunk.document_version,
                            )
                            for chunk in chunks
                        ]
                    )
                    session.flush()
                    result = self.libraries.base_read(session, base)
                published = True
            finally:
                if not published:
                    self.store.retire(name)
        if old_name:
            self.store.retire(old_name)
        return result

    def clear(self, actor: Actor, kb: str) -> None:
        self.libraries.manager(actor)
        with self.store.lock:
            with self.database.transaction() as session:
                reserve_writer(session, KnowledgeBase.__table__)
                self.libraries.require_base(session, kb, actor).updated_at = utc_now()
                current = session.get(LibraryVectorIndex, kb)
                name = current.collection_name if current else None
                session.execute(
                    delete(LibraryVectorMembership).where(
                        LibraryVectorMembership.knowledge_base_id == kb
                    )
                )
                session.execute(
                    delete(LibraryVectorIndex).where(LibraryVectorIndex.knowledge_base_id == kb)
                )
            if name:
                self.store.retire(name)

    def query(
        self, kb: str, data: SearchRequest, authorize: Callable[[Session], KnowledgeBase]
    ) -> SearchResult:
        with ExitStack() as lease:
            with self.store.lock, self.database.transaction() as session:
                status = self.libraries.base_read(session, authorize(session))
                if status.vector_status not in {"ready", "partial"}:
                    raise ConflictError(
                        "knowledge_vector_not_ready",
                        "向量索引尚未建立、已过期或连接已停用，请先检查并重建索引。",
                    )
                index = session.get(LibraryVectorIndex, kb)
                assert index is not None
                generation, name = index.generation, index.collection_name
                source = source_digest(session, kb)
                ids = list(
                    session.scalars(
                        select(LibraryVectorMembership.chunk_id).where(
                            LibraryVectorMembership.knowledge_base_id == kb,
                            LibraryVectorMembership.generation == generation,
                        )
                    )
                )
                config = self.connections.resolve_embedding(
                    index.connection_id, index.config_revision, db=session
                )
                lease.enter_context(self.store.use(name))
            query = embed_texts(config, [data.question])[0]
            limit = 30 if data.strategy == "hybrid" else data.top_k
            candidates = self.store.query(name, query, ids, limit)
            with self.database.transaction() as session:
                base = authorize(session)
                current = session.get(LibraryVectorIndex, kb)
                if (
                    current is None
                    or current.generation != generation
                    or source_digest(session, kb) != source
                    or self.libraries.base_read(session, base).vector_status
                    not in {"ready", "partial"}
                ):
                    raise ConflictError(
                        "knowledge_index_changed", "检索期间索引或资料已变化，请重新检索。"
                    )
                self.connections.resolve_embedding(
                    config.connection_id,
                    config.config_revision,
                    config.credential_revision,
                    db=session,
                )
                rows: dict[str, dict] = dict(
                    session.execute(
                        select(LibraryChunk.id, LibraryChunk.snapshot)
                        .join(
                            LibraryVectorMembership,
                            LibraryVectorMembership.chunk_id == LibraryChunk.id,
                        )
                        .where(
                            LibraryVectorMembership.knowledge_base_id == kb,
                            LibraryVectorMembership.generation == generation,
                            LibraryChunk.id.in_([id for id, _ in candidates]),
                        )
                    ).all()
                )
                if set(rows) != {id for id, _ in candidates}:
                    raise ConflictError(
                        "knowledge_index_changed", "检索期间片段已变化，请重新检索。"
                    )
                hits = [
                    SearchHit(
                        rank=rank,
                        score=distance,
                        score_kind="cosine_distance_lower_better",
                        chunk=Chunk.model_validate(rows[id]),
                    )
                    for rank, (id, distance) in enumerate(candidates, 1)
                ]
                if data.strategy == "hybrid":
                    lexical = lexical_search(session, kb, data.question, limit)
                    hits = fuse_rankings([lexical, hits], data.top_k)
                return SearchResult(
                    knowledge_base_id=kb,
                    strategy="hybrid" if data.strategy == "hybrid" else "vector",
                    hits=hits,
                )

    def prune(self, kb: str) -> None:
        """立即移除可见关系，物理清理失败可重试。"""
        with self.store.lock:
            with self.database.transaction() as db:
                index = db.get(LibraryVectorIndex, kb)
                if index is None:
                    return
                name = index.collection_name
                ids = set(
                    db.scalars(
                        select(LibraryVectorMembership.chunk_id).where(
                            LibraryVectorMembership.knowledge_base_id == kb,
                            LibraryVectorMembership.generation == index.generation,
                        )
                    )
                )
            try:
                self.store.prune(name, ids)
            except Exception:
                logger.warning("Knowledge vector pruning deferred: %s", name)

    def reconcile(self) -> None:
        """持有进程锁后、开始服务前执行一次。"""
        with self.store.lock:
            names = self.store.names()
            with self.database.transaction() as db:
                indexes = list(db.scalars(select(LibraryVectorIndex)))
                published = {index.collection_name for index in indexes}
                libraries = []
                for index in indexes:
                    if index.collection_name not in names:
                        db.execute(
                            delete(LibraryVectorMembership).where(
                                LibraryVectorMembership.knowledge_base_id == index.knowledge_base_id
                            )
                        )
                        db.delete(index)
                        logger.warning(
                            "Knowledge vector index missing; rebuild required: %s",
                            index.knowledge_base_id,
                        )
                    else:
                        libraries.append(index.knowledge_base_id)
            for name in names - published:
                self.store.retire(name)
            for kb in libraries:
                self.prune(kb)
