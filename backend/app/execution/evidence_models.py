from sqlalchemy import JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import NumericID, UUIDText


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
