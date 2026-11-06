"""Durable keyword jobs: short claims, bounded work, and atomic per-file publication."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.errors import ConflictError, InvalidInputError, NotFoundError, ServiceError
from app.infrastructure.database.transactions import reserve_writer
from app.knowledge.chunking import ChunkLimitExceeded, split_document
from app.knowledge.contracts import Chunk, ChunkingRules, KnowledgeDocument
from app.knowledge.lexical import lexical_terms, lexical_version
from app.knowledge.loading import text_document
from app.knowledge.models import (
    KnowledgeBase,
    LibraryChunk,
    LibraryDocument,
    LibraryVectorMembership,
    ProcessingBatch,
    ProcessingItem,
)
from app.knowledge.schemas import (
    ChunkPreviewRead,
    ChunkPreviewRequest,
    ProcessingBatchRead,
    ProcessingItemRead,
    ProcessingRequest,
    effective_rules,
)
from app.values import new_uuid, utc_now

if TYPE_CHECKING:
    from app.knowledge.service import KnowledgeService

logger = logging.getLogger(__name__)
ACTIVE = ("queued", "running")


class KnowledgeProcessingService:
    """Own persistent jobs; the lifespan scanner only decides when to run one."""

    def __init__(self, knowledge: KnowledgeService):
        self.knowledge = knowledge

    @staticmethod
    def read(session: Session, batch: ProcessingBatch) -> ProcessingBatchRead:
        items = list(
            session.scalars(
                select(ProcessingItem)
                .where(ProcessingItem.batch_id == batch.id)
                .order_by(ProcessingItem.created_at, ProcessingItem.id)
            )
        )
        statuses = {item.status for item in items}
        if "running" in statuses:
            status = "running"
        elif "queued" in statuses:
            status = "queued"
        elif statuses == {"succeeded"}:
            status = "succeeded"
        elif "succeeded" in statuses:
            status = "partial"
        elif statuses == {"cancelled"}:
            status = "cancelled"
        else:
            status = "failed"
        return ProcessingBatchRead(
            id=batch.id,
            status=status,
            rules=batch.rules,
            created_at=batch.created_at,
            items=[
                ProcessingItemRead(
                    id=i.id,
                    document_id=i.document_id,
                    filename=i.filename,
                    status=i.status,
                    error=i.error,
                )
                for i in items
            ],
        )

    def submit(self, actor: Actor, kb: str, data: ProcessingRequest) -> ProcessingBatchRead:
        """Freeze effective rules and an explicit file set before acknowledging enqueue."""
        payload = data.model_dump(mode="json", exclude={"client_request_id"})
        if data.rules is None:
            payload.pop("rules")  # Preserve idempotency of submissions accepted before preview.
        if data.document_ids and len(set(data.document_ids)) != len(data.document_ids):
            raise InvalidInputError("knowledge_duplicate_document", "处理文件不能重复。")
        with self.knowledge.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            base = self.knowledge.require_base(session, kb, actor)
            old = session.scalar(
                select(ProcessingBatch).where(
                    ProcessingBatch.knowledge_base_id == kb,
                    ProcessingBatch.client_request_id == str(data.client_request_id),
                )
            )
            if old:
                if old.request != payload:
                    raise ConflictError(
                        "knowledge_request_conflict", "该处理标识已用于不同文件或处理方式。"
                    )
                return self.read(session, old)
            query = select(LibraryDocument).where(LibraryDocument.knowledge_base_id == kb)
            if data.document_ids:
                query = query.where(LibraryDocument.id.in_([str(id) for id in data.document_ids]))
            else:
                query = query.where(LibraryDocument.active_job_id.is_(None))
                if not data.reprocess:
                    query = query.where(
                        LibraryDocument.processing_state.in_(["pending", "failed", "interrupted"])
                    )
            docs = list(
                session.scalars(query.order_by(LibraryDocument.created_at, LibraryDocument.id))
            )
            if data.document_ids and len(docs) != len(data.document_ids):
                raise NotFoundError("knowledge_document_not_found", "部分文件不存在，请刷新列表。")
            if any(doc.active_job_id for doc in docs):
                raise ConflictError("knowledge_processing_busy", "所选文件已有处理中任务。")
            docs = [doc for doc in docs if data.reprocess or doc.processing_state != "ready"]
            if not docs:
                raise InvalidInputError(
                    "knowledge_nothing_pending", "没有待处理文件；如需重新切分，请选择重新处理。"
                )
            batch = ProcessingBatch(
                id=new_uuid(),
                knowledge_base_id=kb,
                client_request_id=str(data.client_request_id),
                request=payload,
                rules={
                    **(
                        data.rules
                        or effective_rules(
                            base.chunk_size, base.chunk_overlap, base.min_section_chars
                        )
                    ).model_dump(),
                    "split_version": 2,
                },
            )
            session.add(batch)
            session.flush()
            for doc in docs:
                item = ProcessingItem(
                    id=new_uuid(),
                    batch_id=batch.id,
                    document_id=doc.id,
                    filename=self.knowledge.document_read(session, doc).filename,
                    source_hash=doc.content_hash,
                    status="queued",
                )
                session.add(item)
                doc.active_job_id, doc.processing_state, doc.processing_error = (
                    item.id,
                    "queued",
                    None,
                )
            session.flush()
            return self.read(session, batch)

    def batches(self, actor: Actor, kb: str) -> list[ProcessingBatchRead]:
        """Return recent batches; per-file state remains available for older work."""
        with self.knowledge.database.transaction() as session:
            self.knowledge.require_base(session, kb, actor)
            return [
                self.read(session, row)
                for row in session.scalars(
                    select(ProcessingBatch)
                    .where(ProcessingBatch.knowledge_base_id == kb)
                    .order_by(ProcessingBatch.created_at.desc(), ProcessingBatch.id)
                    .limit(20)
                )
            ]

    def get(self, actor: Actor, kb: str, id: str) -> ProcessingBatchRead:
        with self.knowledge.database.transaction() as session:
            self.knowledge.require_base(session, kb, actor)
            row = session.get(ProcessingBatch, id)
            if row is None or row.knowledge_base_id != kb:
                raise NotFoundError("knowledge_job_not_found", "处理任务不存在。")
            return self.read(session, row)

    def cancel(self, actor: Actor, kb: str, id: str) -> ProcessingBatchRead:
        """Invalidate commit permits; never discard previously published files."""
        with self.knowledge.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            self.knowledge.require_base(session, kb, actor)
            batch = session.get(ProcessingBatch, id)
            if batch is None or batch.knowledge_base_id != kb:
                raise NotFoundError("knowledge_job_not_found", "处理任务不存在。")
            for item in session.scalars(
                select(ProcessingItem).where(
                    ProcessingItem.batch_id == id, ProcessingItem.status.in_(ACTIVE)
                )
            ):
                item.status, item.error = "cancelled", "任务已取消，已生效内容保留。"
                doc = session.get(LibraryDocument, item.document_id)
                if doc and doc.active_job_id == item.id:
                    doc.active_job_id = None
                    doc.processing_state = "ready" if doc.snapshot else "pending"
                    doc.processing_error = None
            session.flush()
            return self.read(session, batch)

    def recover(self) -> None:
        """Queued work survives restart; uncertain running work requires explicit retry."""
        with self.knowledge.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            for item in session.scalars(
                select(ProcessingItem).where(ProcessingItem.status == "running")
            ):
                item.status, item.error = (
                    "interrupted",
                    "服务重启，处理已中断，请重试；原有可用内容保留。",
                )
                doc = session.get(LibraryDocument, item.document_id)
                if doc and doc.active_job_id == item.id:
                    doc.active_job_id, doc.processing_state, doc.processing_error = (
                        None,
                        "interrupted",
                        item.error,
                    )

    def run_next(self) -> bool:
        """Claim at most one item. No parsing or file I/O holds a database transaction."""
        with self.knowledge.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            item = session.scalar(
                select(ProcessingItem)
                .where(ProcessingItem.status == "queued")
                .order_by(ProcessingItem.created_at, ProcessingItem.id)
                .limit(1)
            )
            if item is None:
                return False
            id = item.id
            doc = session.get(LibraryDocument, item.document_id)
            if doc is None or doc.active_job_id != id or doc.content_hash != item.source_hash:
                item.status, item.error = "cancelled", "文件或任务已变化，未发布处理结果。"
                if doc and doc.active_job_id == id:
                    doc.active_job_id = None
                    doc.processing_state = "ready" if doc.snapshot else "pending"
                    doc.processing_error = item.error
                return True
            item.status, doc.processing_state = "running", "processing"
            batch = session.get(ProcessingBatch, item.batch_id)
            assert batch is not None
            file_id, document_id, filename, rules = doc.file_id, doc.id, item.filename, batch.rules
        try:
            document, chunks = self.prepare(file_id, document_id, filename, rules)
            tokens = [" ".join(lexical_terms(chunk.index_text)) for chunk in chunks]
            self.publish(id, document, chunks, tokens, rules)
        except Exception as error:
            message = (
                error.message
                if isinstance(error, ServiceError)
                else "文档处理失败，请重试；原件和已生效内容保留。"
            )
            logger.warning("Knowledge processing failed item=%s type=%s", id, type(error).__name__)
            self.fail(id, message)
        return True

    def prepare(
        self, file_id: str, document_id: str, filename: str, rules: dict
    ) -> tuple[KnowledgeDocument, tuple[Chunk, ...]]:
        """Shared bounded computation; neither preview nor parsing publishes partial content."""
        document = text_document(self.knowledge.files.read(file_id), document_id, filename)
        args = (
            {"min_section_chars": rules["min_section_chars"]}
            if rules.get("split_version") == 2
            else {}
        )
        try:
            chunks = split_document(
                document,
                ChunkingRules(
                    chunk_tokens=rules["chunk_size"], overlap_tokens=rules["chunk_overlap"]
                ),
                len,
                max_chunks=5000,
                **args,
            )
        except ChunkLimitExceeded:
            raise InvalidInputError(
                "knowledge_chunk_quota_exceeded",
                "单份文档切分超过5000片段，请增大切分长度或减小重叠。",
            ) from None
        return document, chunks

    def preview(
        self, actor: Actor, kb: str, id: str, data: ChunkPreviewRequest
    ) -> ChunkPreviewRead:
        """Read one original and return a bounded page without changing any ready state."""
        with self.knowledge.database.transaction() as session:
            base = self.knowledge.require_base(session, kb, actor)
            doc = session.get(LibraryDocument, id)
            if doc is None or doc.knowledge_base_id != kb:
                raise NotFoundError("knowledge_document_not_found", "文件不存在。")
            rules = data.rules or effective_rules(
                base.chunk_size, base.chunk_overlap, base.min_section_chars
            )
            file_id, source_hash = doc.file_id, doc.content_hash
            filename = self.knowledge.document_read(session, doc).filename
        _, chunks = self.prepare(file_id, id, filename, {**rules.model_dump(), "split_version": 2})
        with self.knowledge.database.transaction() as session:
            self.knowledge.require_base(session, kb, actor)
            doc = session.get(LibraryDocument, id)
            if doc is None or doc.knowledge_base_id != kb:
                raise NotFoundError("knowledge_document_not_found", "文件已删除，请刷新列表。")
            if doc.content_hash != source_hash:
                raise ConflictError("knowledge_source_changed", "原件已变化，请重新预览。")
        lengths = [len(chunk.text) for chunk in chunks]
        return ChunkPreviewRead(
            document_id=id,
            filename=filename,
            rules=rules,
            chunk_count=len(chunks),
            short_chunk_count=sum(length < rules.min_section_chars for length in lengths),
            merged_chunk_count=sum(len(chunk.spans) > 1 for chunk in chunks),
            min_length=min(lengths, default=0),
            max_length=max(lengths, default=0),
            offset=data.offset,
            has_more=data.offset + 20 < len(chunks),
            chunks=list(chunks[data.offset : data.offset + 20]),
        )

    def fail(self, id: str, message: str) -> None:
        with self.knowledge.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            item = session.get(ProcessingItem, id)
            if item is None or item.status != "running":
                return
            item.status, item.error = "failed", message
            doc = session.get(LibraryDocument, item.document_id)
            if doc and doc.active_job_id == id:
                doc.active_job_id, doc.processing_state, doc.processing_error = (
                    None,
                    "failed",
                    message,
                )

    def publish(
        self,
        id: str,
        document: KnowledgeDocument,
        chunks: tuple[Chunk, ...],
        tokens: list[str],
        rules: dict,
    ) -> None:
        """Replace exactly one file atomically, after rechecking its live commit permit."""
        with self.knowledge.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            item = session.get(ProcessingItem, id)
            doc = session.get(LibraryDocument, document.id)
            if item is None or item.status != "running" or doc is None or doc.active_job_id != id:
                return
            if doc.content_hash != item.source_hash or document.original_sha256 != item.source_hash:
                raise ConflictError("knowledge_source_changed", "原件已变化，请重新发起处理。")
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(LibraryChunk)
                    .join(LibraryDocument)
                    .where(
                        LibraryDocument.knowledge_base_id == doc.knowledge_base_id,
                        LibraryDocument.id != doc.id,
                    )
                )
                or 0
            )
            if count + len(chunks) > 5000:
                raise InvalidInputError(
                    "knowledge_quota_exceeded", "知识库超过5000个片段，请调整规则或减少文档。"
                )
            old_ids = select(LibraryChunk.id).where(LibraryChunk.document_id == doc.id)
            session.execute(
                delete(LibraryVectorMembership).where(LibraryVectorMembership.chunk_id.in_(old_ids))
            )
            session.execute(
                text(
                    "DELETE FROM knowledge_fts WHERE chunk_id IN (SELECT id FROM knowledge_chunks WHERE document_id=:doc)"
                ),
                {"doc": doc.id},
            )
            session.execute(delete(LibraryChunk).where(LibraryChunk.document_id == doc.id))
            for position, (chunk, words) in enumerate(zip(chunks, tokens, strict=True)):
                session.add(
                    LibraryChunk(
                        id=chunk.id,
                        document_id=doc.id,
                        position=position,
                        snapshot=chunk.model_dump(mode="json"),
                    )
                )
                session.execute(
                    text(
                        "INSERT INTO knowledge_fts(chunk_id,knowledge_base_id,tokens) VALUES (:chunk,:kb,:tokens)"
                    ),
                    {"chunk": chunk.id, "kb": doc.knowledge_base_id, "tokens": words},
                )
            doc.snapshot, doc.title, doc.lexical_version = (
                document.model_dump(mode="json"),
                document.title,
                lexical_version(),
            )
            doc.processing_rules = rules
            doc.active_job_id, doc.processing_state, doc.processing_error = None, "ready", None
            item.status, item.error = "succeeded", None
            base = session.get(KnowledgeBase, doc.knowledge_base_id)
            assert base is not None
            base.updated_at = utc_now()
            kb = doc.knowledge_base_id
        if self.knowledge._vectors is not None:
            self.knowledge.vectors.prune(kb)
