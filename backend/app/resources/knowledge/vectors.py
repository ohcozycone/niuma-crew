from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from threading import BoundedSemaphore, Event

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.auth.work_authorizations import authorize_work
from app.common.errors import ConflictError, InvalidInputError, NotFoundError, ServiceError
from app.common.values import digest, new_uuid, utc_now
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.infrastructure.llm.embeddings import (
    BATCH_SIZE,
    VECTOR_DIMENSIONS,
    EmbeddingConfig,
    embed_texts,
    normalized_vector,
)
from app.resources.knowledge.contracts import Chunk
from app.resources.knowledge.lexical import lexical_search
from app.resources.knowledge.libraries import KnowledgeLibraries
from app.resources.knowledge.models import (
    KnowledgeBase,
    LibraryChunk,
    LibraryDocument,
    LibraryVectorIndex,
    LibraryVectorMembership,
    VectorEmbedding,
    VectorJob,
)
from app.resources.knowledge.retrieval import fuse_rankings
from app.resources.knowledge.schemas import (
    EmbeddingConnectionRead,
    SearchHit,
    SearchRequest,
    SearchResult,
    VectorJobRead,
)
from app.resources.knowledge.sources import source_digest
from app.resources.knowledge.vector_store import PREFIX, KnowledgeVectorStore
from app.resources.model_connections.references import embedding_connections
from app.resources.model_connections.service import ModelConnectionService

logger = logging.getLogger(__name__)
ACTIVE = ("queued", "running")


def embedding_fingerprint(config: EmbeddingConfig) -> str:
    return digest([config.base_url, config.model_id, VECTOR_DIMENSIONS, "cosine"])


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
        self.stopping = Event()

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

    def build(
        self, actor: Actor, kb: str, connection_id: str, client_request_id: str
    ) -> VectorJobRead:
        """Acknowledge only after a durable, idempotent enqueue; no provider I/O."""
        owner = self.libraries.manager(actor)
        with self.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            self.libraries.require_base(session, kb, actor)
            previous = session.scalar(
                select(VectorJob).where(
                    VectorJob.knowledge_base_id == kb,
                    VectorJob.client_request_id == client_request_id,
                )
            )
            if previous:
                if previous.connection_id != connection_id:
                    raise ConflictError(
                        "knowledge_request_conflict", "该提交标识已用于其他向量模型。"
                    )
                return VectorJobRead.model_validate(previous)
            if session.scalar(
                select(VectorJob.id).where(
                    VectorJob.knowledge_base_id == kb, VectorJob.status.in_(ACTIVE)
                )
            ):
                raise ConflictError("knowledge_build_busy", "本库已有向量任务，请等待或取消。")
            config = self.connections.resolve_embedding(connection_id, db=session)
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(LibraryChunk)
                    .join(LibraryDocument)
                    .where(LibraryDocument.knowledge_base_id == kb)
                )
                or 0
            )
            if not count:
                raise InvalidInputError(
                    "knowledge_empty", "请先处理文档生成关键词索引，再建立向量索引。"
                )
            current = session.get(LibraryVectorIndex, kb)
            job = VectorJob(
                knowledge_base_id=kb,
                client_request_id=client_request_id,
                user_id=owner,
                session_id=actor.session_id,
                connection_id=connection_id,
                config_revision=config.config_revision,
                credential_revision=config.credential_revision,
                source_digest=source_digest(session, kb),
                previous_generation=current.generation if current else None,
                embedding_fingerprint=embedding_fingerprint(config),
                chunk_count=count,
            )
            session.add(job)
            session.flush()
            return VectorJobRead.model_validate(job)

    def jobs(self, actor: Actor, kb: str) -> list[VectorJobRead]:
        with self.database.transaction() as session:
            self.libraries.require_base(session, kb, actor)
            return [
                VectorJobRead.model_validate(job)
                for job in session.scalars(
                    select(VectorJob)
                    .where(VectorJob.knowledge_base_id == kb)
                    .order_by(VectorJob.created_at.desc(), VectorJob.id)
                    .limit(20)
                )
            ]

    def get_job(self, actor: Actor, kb: str, id: str) -> VectorJobRead:
        with self.database.transaction() as session:
            self.libraries.require_base(session, kb, actor)
            return VectorJobRead.model_validate(self.require_job(session, kb, id))

    @staticmethod
    def require_job(session: Session, kb: str, id: str) -> VectorJob:
        job = session.get(VectorJob, id)
        if job is None or job.knowledge_base_id != kb:
            raise NotFoundError("knowledge_job_not_found", "向量任务不存在。")
        return job

    def cancel(self, actor: Actor, kb: str, id: str) -> VectorJobRead:
        self.libraries.manager(actor)
        with self.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            self.libraries.require_base(session, kb, actor)
            job = self.require_job(session, kb, id)
            if job.status in ACTIVE:
                job.status, job.error = "cancelled", "任务已取消，原索引保留。"
            session.flush()
            return VectorJobRead.model_validate(job)

    def recover(self) -> None:
        """Retain queued jobs and paid checkpoints; never silently retry unknown calls."""
        self.stopping.clear()
        with self.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            for job in session.scalars(select(VectorJob).where(VectorJob.status == "running")):
                job.status, job.error = (
                    "interrupted",
                    "服务重启，任务已中断；请重试，已完成向量会复用。",
                )

    def run_next(self) -> bool:
        if not self.build_slot.acquire(blocking=False):
            return False
        try:
            with self.database.transaction() as session:
                reserve_writer(session, KnowledgeBase.__table__)
                job = session.scalar(
                    select(VectorJob)
                    .where(VectorJob.status == "queued")
                    .order_by(VectorJob.created_at, VectorJob.id)
                    .limit(1)
                )
                if job is None:
                    return False
                id = job.id
                job.status = "running"
            try:
                self._build(id)
            except Exception as error:
                logger.warning(
                    "Knowledge vector job failed id=%s type=%s", id, type(error).__name__
                )
                with self.database.transaction() as session:
                    reserve_writer(session, KnowledgeBase.__table__)
                    job = session.get(VectorJob, id)
                    if job and job.status == "running":
                        job.status = "interrupted" if self.stopping.is_set() else "failed"
                        job.error = (
                            error.message
                            if isinstance(error, ServiceError)
                            else "向量构建失败，请重试；原索引保留。"
                        )
                        job.error_code = (
                            error.code
                            if isinstance(error, ServiceError)
                            else "knowledge_build_failed"
                        )
            return True
        finally:
            self.build_slot.release()

    def guard(self, session: Session, id: str) -> tuple[VectorJob, EmbeddingConfig]:
        job = session.get(VectorJob, id)
        if self.stopping.is_set():
            raise ConflictError(
                "knowledge_build_interrupted", "服务正在停止，请稍后重试；已完成向量保留。"
            )
        if job is None or job.status != "running":
            raise ConflictError("knowledge_build_cancelled", "任务已取消，原索引保留。")
        actor = authorize_work(session, job.user_id, job.session_id, permission="knowledge:manage")
        self.libraries.require_base(session, job.knowledge_base_id, actor)
        current = session.get(LibraryVectorIndex, job.knowledge_base_id)
        if (
            source_digest(session, job.knowledge_base_id) != job.source_digest
            or (current.generation if current else None) != job.previous_generation
        ):
            raise ConflictError(
                "knowledge_build_changed", "构建期间资料或索引已变化，请重新建立索引。"
            )
        config = self.connections.resolve_embedding(
            job.connection_id, job.config_revision, job.credential_revision, db=session
        )
        return job, config

    def _build(self, id: str) -> None:
        self.store.client  # Acquire the process lock before any charged request.
        with self.database.transaction() as session:
            job, config = self.guard(session, id)
            kb, fingerprint = job.knowledge_base_id, job.embedding_fingerprint
            chunks = [
                Chunk.model_validate(row.snapshot)
                for row in session.scalars(
                    select(LibraryChunk)
                    .join(LibraryDocument)
                    .where(LibraryDocument.knowledge_base_id == kb)
                    .order_by(LibraryChunk.id)
                )
            ]
            cached = {
                row.content_hash: row.vector
                for row in session.scalars(
                    select(VectorEmbedding).where(
                        VectorEmbedding.knowledge_base_id == kb,
                        VectorEmbedding.embedding_fingerprint == fingerprint,
                    )
                )
            }
            old = session.get(LibraryVectorIndex, kb)
            old_name = (
                old.collection_name if old and old.embedding_fingerprint == fingerprint else None
            )
        hashes = [digest(chunk.text) for chunk in chunks]
        needed = dict(zip(hashes, [chunk.text for chunk in chunks], strict=True))
        vectors: dict[str, list[float]] = {}
        for key, vector in cached.items():
            if key in needed:
                try:
                    vectors[key] = normalized_vector(vector)
                except ValueError:
                    pass
        # Existing installations can reuse the live Chroma generation without another charge.
        if old_name:
            with self.store.use(old_name):
                legacy = self.store.embeddings(old_name, [chunk.id for chunk in chunks])
            for chunk, key in zip(chunks, hashes, strict=True):
                if key not in vectors and chunk.id in legacy:
                    vectors[key] = legacy[chunk.id]
        reused = sum(key in vectors for key in hashes)

        def guard() -> None:
            with self.database.transaction() as session:
                self.guard(session, id)

        def checkpoint(batch: dict[str, list[float]]) -> None:
            with self.database.transaction() as session:
                reserve_writer(session, KnowledgeBase.__table__)
                job, _ = self.guard(session, id)
                for key, vector in batch.items():
                    row = session.get(VectorEmbedding, (kb, fingerprint, key))
                    if row is None:
                        session.add(
                            VectorEmbedding(
                                knowledge_base_id=kb,
                                embedding_fingerprint=fingerprint,
                                content_hash=key,
                                vector=vector,
                            )
                        )
                    else:
                        row.vector = vector
                job.completed_count = sum(key in vectors for key in hashes)
                job.reused_count = reused

        checkpoint(vectors)
        pending = [key for key in needed if key not in vectors]
        for start in range(0, len(pending), BATCH_SIZE):
            keys = pending[start : start + BATCH_SIZE]
            guard()
            embedded = embed_texts(config, [needed[key] for key in keys], guard)
            batch = dict(zip(keys, embedded, strict=True))
            vectors.update(batch)
            checkpoint(batch)
        generation = new_uuid()
        name = PREFIX + digest([kb, generation])[:48]
        published = False
        retired = None
        with self.store.use(name):
            try:
                self.store.build(name, chunks, [vectors[key] for key in hashes])
                with self.store.lock, self.database.transaction() as session:
                    reserve_writer(session, KnowledgeBase.__table__)
                    job, _ = self.guard(session, id)
                    current = session.get(LibraryVectorIndex, kb)
                    retired = current.collection_name if current else None
                    session.execute(
                        delete(LibraryVectorMembership).where(
                            LibraryVectorMembership.knowledge_base_id == kb
                        )
                    )
                    if current is None:
                        current = LibraryVectorIndex(knowledge_base_id=kb)
                        session.add(current)
                    current.connection_id, current.config_revision = (
                        config.connection_id,
                        config.config_revision,
                    )
                    current.source_digest, current.chunk_count = job.source_digest, len(chunks)
                    current.generation, current.collection_name = generation, name
                    current.embedding_fingerprint = fingerprint
                    session.add_all(
                        [
                            LibraryVectorMembership(
                                chunk_id=chunk.id,
                                knowledge_base_id=kb,
                                generation=generation,
                                document_id=chunk.document_id,
                                document_version=chunk.document_version,
                            )
                            for chunk in chunks
                        ]
                    )
                    job.status = "succeeded"
                    # Bound checkpoints to the published source and model after success.
                    session.execute(
                        delete(VectorEmbedding).where(
                            VectorEmbedding.knowledge_base_id == kb,
                            or_(
                                VectorEmbedding.embedding_fingerprint != fingerprint,
                                VectorEmbedding.content_hash.not_in(list(needed)),
                            ),
                        )
                    )
                published = True
            finally:
                if not published:
                    self.store.retire(name)
        if retired:
            self.store.retire(retired)

    def clear(self, actor: Actor, kb: str) -> None:
        self.libraries.manager(actor)
        with self.store.lock:
            with self.database.transaction() as session:
                reserve_writer(session, KnowledgeBase.__table__)
                self.libraries.require_base(session, kb, actor).updated_at = utc_now()
                for job in session.scalars(
                    select(VectorJob).where(
                        VectorJob.knowledge_base_id == kb, VectorJob.status.in_(ACTIVE)
                    )
                ):
                    job.status, job.error = "cancelled", "向量索引已移除，任务已取消。"
                session.execute(
                    delete(VectorEmbedding).where(VectorEmbedding.knowledge_base_id == kb)
                )
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
                reserve_writer(db, KnowledgeBase.__table__)
                snapshots: list[dict] = list(
                    db.scalars(
                        select(LibraryChunk.snapshot)
                        .join(LibraryDocument)
                        .where(LibraryDocument.knowledge_base_id == kb)
                    )
                )
                content_hashes = [digest(snapshot["text"]) for snapshot in snapshots]
                db.execute(
                    delete(VectorEmbedding).where(
                        VectorEmbedding.knowledge_base_id == kb,
                        VectorEmbedding.content_hash.not_in(content_hashes),
                    )
                )
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
