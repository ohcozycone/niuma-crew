from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import IdentityTimestamps, NumericID, UUIDText


class KnowledgeBase(IdentityTimestamps, Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 100", name="name_valid"),
        UniqueConstraint("created_by_user_id", "client_request_id"),
    )
    created_by_user_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("users.id"), index=True)
    client_request_id: Mapped[str] = mapped_column(UUIDText())
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    chunk_size: Mapped[int | None] = mapped_column(Integer)
    chunk_overlap: Mapped[int | None] = mapped_column(Integer)
    min_section_chars: Mapped[int | None] = mapped_column(Integer)


class RunKnowledgeEvidence(Base):
    __tablename__ = "knowledge_run_evidence"
    run_id: Mapped[str] = mapped_column(
        NumericID(), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[str] = mapped_column(Text, primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(UUIDText())
    document_id: Mapped[str] = mapped_column(UUIDText())
    document_version: Mapped[str] = mapped_column(Text)
    chunk_id: Mapped[str] = mapped_column(Text)
    # 不建实时文档外键以保留历史；使用时仍检查当前来源。
    snapshot: Mapped[dict] = mapped_column(JSON)


class LibraryDocument(IdentityTimestamps, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id", "client_request_id", name="uq_knowledge_documents_request"
        ),
        UniqueConstraint(
            "knowledge_base_id", "content_hash", name="uq_knowledge_documents_content"
        ),
        CheckConstraint(
            "json_valid(snapshot) AND json_type(snapshot) = 'object'", name="snapshot_object"
        ),
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("knowledge_bases.id"), index=True
    )
    client_request_id: Mapped[str] = mapped_column(UUIDText())
    file_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("stored_files.id"), unique=True)
    title: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON)
    lexical_version: Mapped[str] = mapped_column(Text)
    processing_state: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    processing_error: Mapped[str | None] = mapped_column(Text)
    active_job_id: Mapped[str | None] = mapped_column(UUIDText())
    processing_rules: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")


class ProcessingBatch(IdentityTimestamps, Base):
    __tablename__ = "knowledge_processing_batches"
    __table_args__ = (UniqueConstraint("knowledge_base_id", "client_request_id"),)
    knowledge_base_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("knowledge_bases.id"), index=True
    )
    client_request_id: Mapped[str] = mapped_column(UUIDText())
    request: Mapped[dict] = mapped_column(JSON)
    rules: Mapped[dict] = mapped_column(JSON)


class ProcessingItem(IdentityTimestamps, Base):
    __tablename__ = "knowledge_processing_items"
    batch_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("knowledge_processing_batches.id"), index=True
    )
    # 删除来源后保留历史，提交时复核当前文档。
    document_id: Mapped[str] = mapped_column(UUIDText(), index=True)
    filename: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)


class LibraryChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint(
            "json_valid(snapshot) AND json_type(snapshot) = 'object'", name="snapshot_object"
        ),
        UniqueConstraint("document_id", "position"),
    )
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("knowledge_documents.id"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)


class LibraryVectorIndex(Base):
    __tablename__ = "knowledge_vector_indexes"
    knowledge_base_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("knowledge_bases.id"), primary_key=True
    )
    connection_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("model_connections.id"), index=True
    )
    config_revision: Mapped[int] = mapped_column(Integer)
    generation: Mapped[str] = mapped_column(UUIDText())
    source_digest: Mapped[str] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer)
    collection_name: Mapped[str] = mapped_column(Text, unique=True, index=True)
    embedding_fingerprint: Mapped[str] = mapped_column(Text)


class LibraryVectorMembership(Base):
    __tablename__ = "knowledge_vector_memberships"
    chunk_id: Mapped[str] = mapped_column(Text, ForeignKey("knowledge_chunks.id"), primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("knowledge_bases.id"), index=True
    )
    generation: Mapped[str] = mapped_column(UUIDText())
    document_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("knowledge_documents.id"))
    document_version: Mapped[str] = mapped_column(Text)
