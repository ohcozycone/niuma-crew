"""Bounded text ingestion: parse outside transactions, publish original/chunks/FTS together."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast
from uuid import UUID, uuid5

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.errors import ConflictError, InvalidInputError, NotFoundError, ServiceUnavailableError
from app.files.models import StoredFile
from app.files.service import FileService, safe_name
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.knowledge.contracts import Chunk, KnowledgeDocument
from app.knowledge.loading import validate_text_upload
from app.knowledge.models import (
    KnowledgeBase,
    LibraryChunk,
    LibraryDocument,
    LibraryVectorIndex,
    LibraryVectorMembership,
    ProcessingItem,
)
from app.knowledge.samples import sample_files
from app.knowledge.schemas import (
    CitationPreviewRead,
    DocumentDetail,
    DocumentRead,
    LibraryCreate,
    LibraryRead,
    LibraryUpdate,
    ProcessingState,
    SearchHit,
    SearchRequest,
    SearchResult,
    effective_rules,
)
from app.knowledge.vectors import KnowledgeVectorService, index_summary
from app.model_connections.models import ModelConnection
from app.model_connections.service import ModelConnectionService
from app.values import new_uuid, utc_now

MAX_DOCUMENT_BYTES = 128 * 1024
MAX_LIBRARY_DOCUMENTS = 200
MAX_LIBRARY_CHUNKS = 5000


def retained_file_ids(session: Session, candidates: list[StoredFile]) -> set[str]:
    """Called by bootstrap's combined retention policy, not by conversation business."""
    return set(
        session.scalars(
            select(LibraryDocument.file_id).where(
                LibraryDocument.file_id.in_([row.id for row in candidates])
            )
        )
    )


class KnowledgeService:
    """Owner-scoped knowledge operations; even administrators cannot cross owners."""

    def __init__(
        self,
        database: Database,
        files: FileService,
        connections: ModelConnectionService | None = None,
        vector_directory: Path | None = None,
    ):
        self.database, self.files = database, files
        self._vectors = (
            KnowledgeVectorService(
                self,
                connections,
                vector_directory
                or Path(str(database.engine.url.database)).parent / "knowledge-vectors",
            )
            if connections
            else None
        )
        from app.knowledge.access import KnowledgeAccess
        from app.knowledge.assignments import KnowledgeAssignments
        from app.knowledge.evidence import KnowledgeEvidence
        from app.knowledge.processing import KnowledgeProcessingService
        from app.knowledge.search import KnowledgeSearch

        self.processing = KnowledgeProcessingService(self)
        self.assignments = KnowledgeAssignments(self)
        self.access = KnowledgeAccess(self)
        self.evidence = KnowledgeEvidence(self)
        self.retrieval = KnowledgeSearch(self)

    def close(self) -> None:
        if self._vectors is not None:
            self._vectors.store.close()

    @property
    def vectors(self) -> KnowledgeVectorService:
        if self._vectors is None:
            raise ServiceUnavailableError("embedding_not_configured", "向量服务尚未装配。")
        return self._vectors

    @staticmethod
    def owner(actor: Actor) -> str:
        require_permission(actor, "knowledge:use")
        if actor.user_id is None:
            raise NotFoundError("knowledge_not_found", "知识库不存在。")
        return actor.user_id

    def require_base(self, session: Session, id: str, actor: Actor) -> KnowledgeBase:
        owner = self.owner(actor)
        row = session.get(KnowledgeBase, id)
        if row is None or row.owner_user_id != owner:
            raise NotFoundError("knowledge_not_found", "知识库不存在。")
        return row

    @staticmethod
    def base_read(session: Session, row: KnowledgeBase) -> LibraryRead:
        rules = effective_rules(row.chunk_size, row.chunk_overlap, row.min_section_chars)
        document_count = (
            session.scalar(
                select(func.count())
                .select_from(LibraryDocument)
                .where(LibraryDocument.knowledge_base_id == row.id)
            )
            or 0
        )
        chunk_count = (
            session.scalar(
                select(func.count())
                .select_from(LibraryChunk)
                .join(LibraryDocument, LibraryDocument.id == LibraryChunk.document_id)
                .where(LibraryDocument.knowledge_base_id == row.id)
            )
            or 0
        )
        return LibraryRead(
            id=row.id,
            name=row.name,
            description=row.description,
            document_count=document_count,
            chunk_count=chunk_count,
            updated_at=row.updated_at,
            revision=row.revision,
            chunk_size=row.chunk_size,
            chunk_overlap=row.chunk_overlap,
            min_section_chars=row.min_section_chars,
            effective_chunk_size=rules.chunk_size,
            effective_chunk_overlap=rules.chunk_overlap,
            effective_min_section_chars=rules.min_section_chars,
            keyword_document_count=session.scalar(
                select(func.count())
                .select_from(LibraryDocument)
                .where(
                    LibraryDocument.knowledge_base_id == row.id,
                    LibraryDocument.lexical_version != "",
                )
            )
            or 0,
            processing_document_count=session.scalar(
                select(func.count())
                .select_from(LibraryDocument)
                .where(
                    LibraryDocument.knowledge_base_id == row.id,
                    LibraryDocument.active_job_id.is_not(None),
                )
            )
            or 0,
            **index_summary(session, row.id, chunk_count),
        )

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
            vector_ready=bool(
                count
                and session.scalar(
                    select(func.count())
                    .select_from(LibraryVectorMembership)
                    .join(LibraryChunk, LibraryChunk.id == LibraryVectorMembership.chunk_id)
                    .join(
                        LibraryVectorIndex,
                        LibraryVectorIndex.knowledge_base_id
                        == LibraryVectorMembership.knowledge_base_id,
                    )
                    .join(ModelConnection, ModelConnection.id == LibraryVectorIndex.connection_id)
                    .where(
                        LibraryChunk.document_id == row.id,
                        ModelConnection.enabled.is_(True),
                        ModelConnection.capability == "embedding",
                        ModelConnection.config_revision == LibraryVectorIndex.config_revision,
                        LibraryVectorMembership.generation == LibraryVectorIndex.generation,
                    )
                )
                == count
            ),
            processing_rules=row.processing_rules,
        )

    def libraries(self, actor: Actor) -> list[LibraryRead]:
        owner = self.owner(actor)
        with self.database.transaction() as session:
            return [
                self.base_read(session, row)
                for row in session.scalars(
                    select(KnowledgeBase)
                    .where(KnowledgeBase.owner_user_id == owner)
                    .order_by(KnowledgeBase.updated_at.desc(), KnowledgeBase.id)
                )
            ]

    def get(self, actor: Actor, id: str) -> LibraryRead:
        with self.database.transaction() as session:
            return self.base_read(session, self.require_base(session, id, actor))

    def create(self, actor: Actor, data: LibraryCreate) -> LibraryRead:
        owner = self.owner(actor)
        with self.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            old = session.scalar(
                select(KnowledgeBase).where(
                    KnowledgeBase.owner_user_id == owner,
                    KnowledgeBase.client_request_id == str(data.client_request_id),
                )
            )
            if old:
                if old.name != data.name or old.description != data.description:
                    raise ConflictError(
                        "knowledge_request_conflict", "该提交标识已用于其他知识库内容。"
                    )
                return self.base_read(session, old)
            if (
                session.scalar(
                    select(func.count())
                    .select_from(KnowledgeBase)
                    .where(KnowledgeBase.owner_user_id == owner)
                )
                or 0
            ) >= 100:
                raise InvalidInputError(
                    "knowledge_quota_exceeded", "每个账号最多创建 100 个知识库。"
                )
            row = KnowledgeBase(
                owner_user_id=owner,
                client_request_id=str(data.client_request_id),
                name=data.name,
                description=data.description,
            )
            session.add(row)
            session.flush()
            return self.base_read(session, row)

    def documents(self, actor: Actor, id: str) -> list[DocumentRead]:
        with self.database.transaction() as session:
            self.require_base(session, id, actor)
            return [
                self.document_read(session, row)
                for row in session.scalars(
                    select(LibraryDocument)
                    .where(LibraryDocument.knowledge_base_id == id)
                    .order_by(LibraryDocument.created_at.desc(), LibraryDocument.id)
                )
            ]

    def update(self, actor: Actor, id: str, data: LibraryUpdate) -> LibraryRead:
        """Save metadata and validated overrides without rebuilding existing files."""
        try:
            effective_rules(data.chunk_size, data.chunk_overlap, data.min_section_chars)
        except ValueError:
            raise InvalidInputError(
                "knowledge_chunk_rule_invalid",
                "重叠必须小于切分长度，短章节阈值不能超过两者之差；请检查合并后的规则。",
            ) from None
        with self.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            row = self.require_base(session, id, actor)
            if row.revision != data.expected_revision:
                raise ConflictError(
                    "configuration_revision_conflict", "知识库设置已变化，请刷新后再修改。"
                )
            values = data.model_dump(exclude={"expected_revision"})
            if any(getattr(row, key) != value for key, value in values.items()):
                for key, value in values.items():
                    setattr(row, key, value)
                row.revision += 1
                row.updated_at = utc_now()
                session.flush()
            return self.base_read(session, row)

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
        owner = self.owner(actor)
        name = safe_name(name)
        validate_text_upload(data, name)
        sha = hashlib.sha256(data).hexdigest()
        with self.database.transaction() as session:
            self.require_base(session, kb_id, actor)
            old = self.existing(session, kb_id, request_id, sha)
            if old:
                return self.document_read(session, old)
        original = self.files.save(owner, name, data, media_type="text/plain; charset=utf-8")
        with self.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            base = self.require_base(session, kb_id, actor)
            old = self.existing(session, kb_id, request_id, sha)
            if old:
                # The unreferenced staging file follows normal files retention, never an exposed orphan.
                return self.document_read(session, old)
            status = self.base_read(session, base)
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
        self.require_base(session, kb_id, actor)
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
        """Read one current, owner-scoped source fragment without loading a full document."""
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
            self.require_base(session, kb_id, actor).updated_at = utc_now()
        if self._vectors is not None:
            self._vectors.prune(kb_id)

    def import_demo(
        self, actor: Actor, kb_id: str, preset: str, request_id: str
    ) -> list[DocumentRead]:
        self.get(actor, kb_id)
        return [
            self.upload(actor, kb_id, str(uuid5(UUID(request_id), name)), name, data)
            for name, data in sample_files(preset)
        ]

    def search(self, actor: Actor, kb_id: str, data: SearchRequest) -> SearchResult:
        return self.retrieval.search_library(actor, kb_id, data)

    @staticmethod
    def lexical_search(session: Session, kb_id: str, question: str, top_k: int) -> list[SearchHit]:
        from app.knowledge.search import KnowledgeSearch

        return KnowledgeSearch.lexical_search(session, kb_id, question, top_k)
