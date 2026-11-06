"""User-owned libraries and immutable ingested documents; original bytes belong to files."""

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import IdentityTimestamps, NumericID, UUIDText


class KnowledgeBase(IdentityTimestamps, Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 100", name="name_valid"),
        UniqueConstraint("owner_user_id", "client_request_id"),
    )
    owner_user_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("users.id"), index=True)
    client_request_id: Mapped[str] = mapped_column(UUIDText())
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    chunk_size: Mapped[int | None] = mapped_column(Integer)
    chunk_overlap: Mapped[int | None] = mapped_column(Integer)
    min_section_chars: Mapped[int | None] = mapped_column(Integer)


class EmployeeKnowledgeSettings(IdentityTimestamps, Base):
    __tablename__ = "knowledge_employee_settings"
    __table_args__ = (UniqueConstraint("user_id", "agent_id"),)
    user_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("users.id", ondelete="CASCADE"))
    agent_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("agents.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    mode: Mapped[str] = mapped_column(Text, default="on_demand", server_default="on_demand")
    strategy: Mapped[str] = mapped_column(Text, default="auto", server_default="auto")
    top_k: Mapped[int] = mapped_column(Integer, default=6, server_default="6")


class EmployeeKnowledgeLibrary(Base):
    __tablename__ = "knowledge_employee_libraries"
    settings_id: Mapped[str] = mapped_column(
        UUIDText(),
        ForeignKey("knowledge_employee_settings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("knowledge_bases.id", ondelete="RESTRICT"), primary_key=True
    )


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
    # No live document/chunk FK: history survives deletion, but every use checks live identity.
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
    # Keep the history after deletion; commit guards recheck the live document.
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
