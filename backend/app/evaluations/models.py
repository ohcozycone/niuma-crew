"""Assessment ownership, immutable test inputs and separately scored answers."""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import (
    IdentityTimestamps,
    NumericID,
    NumericIdentityTimestamps,
    UTCDateTime,
    UUIDText,
)

BATCH_ACTIVE = ("queued", "running", "cancelling")
CASE_TERMINAL = ("passed", "failed", "error", "cancelled")


class EvaluationBatch(NumericIdentityTimestamps, Base):
    __tablename__ = "evaluation_batches"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "request_id", name="uq_evaluation_request"),
        CheckConstraint("total BETWEEN 1 AND 400", name="evaluation_total_valid"),
        CheckConstraint(
            "status IN ('queued','running','cancelling','completed','failed','cancelled')",
            name="evaluation_status_valid",
        ),
        CheckConstraint(
            "(status IN ('queued','running','cancelling') AND finished_at IS NULL) OR "
            "(status IN ('completed','failed','cancelled') AND finished_at IS NOT NULL)",
            name="evaluation_finish_valid",
        ),
        Index("ix_evaluation_owner_agent", "owner_user_id", "agent_id", "created_at"),
    )
    agent_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("agents.id"))
    owner_user_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("users.id"))
    session_id: Mapped[str | None] = mapped_column(
        UUIDText(), ForeignKey("auth_sessions.id", ondelete="SET NULL")
    )
    request_id: Mapped[str] = mapped_column(UUIDText())
    request_hash: Mapped[str] = mapped_column(Text)
    suite_id: Mapped[str] = mapped_column(Text)
    suite_version: Mapped[str] = mapped_column(Text)
    grader_version: Mapped[str] = mapped_column(Text)
    configuration_hash: Mapped[str] = mapped_column(Text)
    configuration_snapshot: Mapped[dict] = mapped_column(JSON)
    total: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, default="queued")
    error_code: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class EvaluationCase(IdentityTimestamps, Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (
        UniqueConstraint("batch_id", "ordinal", name="uq_evaluation_ordinal"),
        UniqueConstraint("batch_id", "question_id", name="uq_evaluation_question"),
        CheckConstraint("ordinal > 0", name="evaluation_ordinal_positive"),
        CheckConstraint(
            "status IN ('pending','running','passed','failed','error','cancelled')",
            name="evaluation_case_status_valid",
        ),
        Index("ix_evaluation_case_batch", "batch_id", "status", "ordinal"),
    )
    batch_id: Mapped[str] = mapped_column(NumericID(), ForeignKey("evaluation_batches.id"))
    ordinal: Mapped[int] = mapped_column(Integer)
    question_id: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text)
    functions: Mapped[list] = mapped_column(JSON)
    expected: Mapped[list] = mapped_column(JSON)
    run_id: Mapped[str | None] = mapped_column(NumericID(), ForeignKey("runs.id"), unique=True)
    status: Mapped[str] = mapped_column(Text, default="pending")
    answer: Mapped[str | None] = mapped_column(Text)
    grading: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
