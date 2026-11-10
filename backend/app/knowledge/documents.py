from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID, uuid5

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.errors import ConflictError, InvalidInputError, NotFoundError
from app.files.models import StoredFile
from app.files.service import FileService, safe_name
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.knowledge.contracts import Chunk, KnowledgeDocument
from app.knowledge.libraries import KnowledgeLibraries
from app.knowledge.loading import validate_text_upload
from app.knowledge.models import (
    KnowledgeBase,
    LibraryChunk,
    LibraryDocument,
    LibraryVectorIndex,
    LibraryVectorMembership,
    ProcessingItem,
)
from app.knowledge.processing import RULE_FIELDS, can_reuse
from app.knowledge.samples import sample_files
from app.knowledge.schemas import (
    CitationPreviewRead,
    DocumentDetail,
    DocumentRead,
    ProcessingState,
)
from app.model_connections.references import connection_fact
from app.values import new_uuid, utc_now

MAX_DOCUMENT_BYTES = 128 * 1024
MAX_LIBRARY_DOCUMENTS = 200
MAX_LIBRARY_CHUNKS = 5000


def vector_ready_count(db: Session, document: LibraryDocument) -> int:
    index = db.get(LibraryVectorIndex, document.knowledge_base_id)
    connection = connection_fact(db, index.connection_id) if index else None
    if (
        not index
        or not connection
        or not connection.enabled
        or connection.capability != "embedding"
        or connection.config_revision != index.config_revision
    ):
        return 0
    return (
        db.scalar(
            select(func.count())
            .select_from(LibraryVectorMembership)
            .join(LibraryChunk, LibraryChunk.id == LibraryVectorMembership.chunk_id)
            .where(
                LibraryChunk.document_id == document.id,
                LibraryVectorMembership.knowledge_base_id == index.knowledge_base_id,
                LibraryVectorMembership.generation == index.generation,
            )
        )
        or 0
    )


class KnowledgeDocuments:
    def __init__(
        self,
        database: Database,
        files: FileService,
        libraries: KnowledgeLibraries,
        *,
        prune_vectors: Callable[[str], None],
    ) -> None:
        self.database, self.files, self.libraries = database, files, libraries
        self.prune_vectors = prune_vectors

    @staticmethod
    def document_read(session: Session, row: LibraryDocument) -> DocumentRead:
        original = session.get(StoredFile, row.file_id)
        if original is None:
            raise RuntimeError("knowledge original metadata missing")
        count = (
            session.scalar(
                select(func.count())
                .select_from(LibraryChunk)
                .where(LibraryChunk.document_id == row.id)
            )
            or 0
        )
        return DocumentRead(
            id=row.id,
            title=row.title,
            filename=original.name,
            size=original.size,
            content_hash=row.content_hash,
            version=row.snapshot.get("version", ""),
            chunk_count=count,
            created_at=row.created_at,
            processing_state=cast(ProcessingState, row.processing_state),
            processing_error=row.processing_error,
            keyword_ready=bool(row.snapshot.get("version")),
            vector_ready=bool(count and vector_ready_count(session, row) == count),
            processing_rules={
                key: value for key, value in row.processing_rules.items() if key in RULE_FIELDS
            },
            processing_reusable=can_reuse(session, row, row.processing_rules),
        )

    def documents(self, actor: Actor, id: str) -> list[DocumentRead]:
        with self.database.transaction() as session:
            self.libraries.require_base(session, id, actor)
            return [
                self.document_read(session, row)
                for row in session.scalars(
                    select(LibraryDocument)
                    .where(LibraryDocument.knowledge_base_id == id)
                    .order_by(LibraryDocument.created_at.desc(), LibraryDocument.id)
                )
            ]

    @staticmethod
    def existing(session: Session, kb_id: str, request_id: str, sha: str) -> LibraryDocument | None:
        old = session.scalar(
            select(LibraryDocument).where(
                LibraryDocument.knowledge_base_id == kb_id,
                LibraryDocument.client_request_id == request_id,
            )
        )
        if old:
            if old.content_hash != sha:
                raise ConflictError(
                    "knowledge_request_conflict", "该上传标识已用于不同内容，请重新选择文件。"
                )
            return old
        return session.scalar(
            select(LibraryDocument).where(
                LibraryDocument.knowledge_base_id == kb_id, LibraryDocument.content_hash == sha
            )
        )

    def upload(
        self, actor: Actor, kb_id: str, request_id: str, name: str, data: bytes
    ) -> DocumentRead:
        owner = self.libraries.manager(actor)
        name = safe_name(name)
        validate_text_upload(data, name)
        sha = hashlib.sha256(data).hexdigest()
        with self.database.transaction() as session:
            self.libraries.require_base(session, kb_id, actor)
            old = self.existing(session, kb_id, request_id, sha)
            if old:
                return self.document_read(session, old)
        original = self.files.save(owner, name, data, media_type="text/plain; charset=utf-8")
        with self.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            base = self.libraries.require_base(session, kb_id, actor)
            old = self.existing(session, kb_id, request_id, sha)
            if old:
                # 未引用暂存文件由文件保留策略回收，不对用户暴露。
                return self.document_read(session, old)
            status = self.libraries.base_read(session, base)
            if status.document_count >= MAX_LIBRARY_DOCUMENTS:
                raise InvalidInputError(
                    "knowledge_quota_exceeded", "知识库已达到 200 份文档或 5000 个片段上限。"
                )
            row = LibraryDocument(
                id=new_uuid(),
                knowledge_base_id=kb_id,
                client_request_id=request_id,
                file_id=original["id"],
                title=Path(name).stem[:180],
                content_hash=sha,
                snapshot={},
                lexical_version="",
                processing_state="pending",
            )
            session.add(row)
            session.flush()
            base.updated_at = utc_now()
            session.flush()
            return self.document_read(session, row)

    def require_document(
        self, session: Session, actor: Actor, kb_id: str, id: str
    ) -> LibraryDocument:
        self.libraries.require_base(session, kb_id, actor)
        row = session.get(LibraryDocument, id)
        if row is None or row.knowledge_base_id != kb_id:
            raise NotFoundError("knowledge_document_not_found", "文档不存在。")
        return row

    def detail(self, actor: Actor, kb_id: str, id: str) -> DocumentDetail:
        with self.database.transaction() as session:
            row = self.require_document(session, actor, kb_id, id)
            chunks = [
                Chunk.model_validate(c.snapshot)
                for c in session.scalars(
                    select(LibraryChunk)
                    .where(LibraryChunk.document_id == id)
                    .order_by(LibraryChunk.position)
                )
            ]
            return DocumentDetail(
                **self.document_read(session, row).model_dump(),
                document=KnowledgeDocument.model_validate(row.snapshot) if row.snapshot else None,
                chunks=chunks,
            )

    def citation_preview(
        self, actor: Actor, kb_id: str, id: str, chunk_id: str
    ) -> CitationPreviewRead:
        with self.database.transaction() as session:
            document = self.require_document(session, actor, kb_id, id)
            row = session.get(LibraryChunk, chunk_id)
            if (
                row is None
                or row.document_id != document.id
                or row.snapshot.get("document_version") != document.snapshot.get("version")
            ):
                raise NotFoundError("knowledge_chunk_not_found", "引用片段已不存在或已重新处理。")
            chunk = Chunk.model_validate(row.snapshot)
            return CitationPreviewRead(
                title=chunk.title[:300],
                locator=chunk.locator[:600],
                excerpt=chunk.text[:600],
                has_more=len(chunk.text) > 600,
                source_url=f"/knowledge/{kb_id}/documents/{id}?chunk={chunk.id}",
            )

    def download(self, actor: Actor, kb_id: str, id: str) -> tuple[str, bytes]:
        with self.database.transaction() as session:
            row = self.require_document(session, actor, kb_id, id)
            file_id = row.file_id
            name = self.document_read(session, row).filename
        return name, self.files.read(file_id)

    def remove(self, actor: Actor, kb_id: str, id: str) -> None:
        self.libraries.manager(actor)
        with self.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            row = self.require_document(session, actor, kb_id, id)
            for item in session.scalars(
                select(ProcessingItem).where(
                    ProcessingItem.document_id == id,
                    ProcessingItem.status.in_(["queued", "running"]),
                )
            ):
                item.status = "cancelled"
                item.error = "文件已删除，处理已取消。"
            session.execute(
                delete(LibraryVectorMembership).where(
                    LibraryVectorMembership.chunk_id.in_(
                        select(LibraryChunk.id).where(LibraryChunk.document_id == id)
                    )
                )
            )
            session.execute(
                text(
                    "DELETE FROM knowledge_fts WHERE chunk_id IN (SELECT id FROM knowledge_chunks WHERE document_id=:doc)"
                ),
                {"doc": id},
            )
            session.execute(delete(LibraryChunk).where(LibraryChunk.document_id == id))
            session.delete(row)
            self.libraries.require_base(session, kb_id, actor).updated_at = utc_now()
        self.prune_vectors(kb_id)

    def import_demo(
        self, actor: Actor, kb_id: str, preset: str, request_id: str
    ) -> list[DocumentRead]:
        self.libraries.get(actor, kb_id)
        return [
            self.upload(actor, kb_id, str(uuid5(UUID(request_id), name)), name, data)
            for name, data in sample_files(preset)
        ]
