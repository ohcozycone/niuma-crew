"""Execution identities, frozen inputs, observed actions and stable outputs."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import (
    IdentityTimestamps,
    NumericID,
    NumericIdentityTimestamps,
    UTCDateTime,
    UUIDText,
)

ACTIVE = ("queued", "running", "cancelling")
TERMINAL = ("succeeded", "failed", "cancelled", "interrupted")


class Run(NumericIdentityTimestamps, Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("id BETWEEN 100000000000 AND 999999999999", name="numeric_id_range"),
        UniqueConstraint(
            "initiated_by_user_id", "operation", "client_request_id", name="uq_runs_request"
        ),
        UniqueConstraint(
            "owner_user_id", "agent_id", "origin_kind", "id", name="uq_runs_retry_identity"
        ),
        ForeignKeyConstraint(
            ["owner_user_id", "agent_id", "origin_kind", "retry_of_run_id"],
            ["runs.owner_user_id", "runs.agent_id", "runs.origin_kind", "runs.id"],
        ),
        CheckConstraint(
            "status IN ('queued','running','cancelling','succeeded','failed','cancelled','interrupted')",
            name="status_valid",
        ),
        CheckConstraint(
            "(status IN ('queued','running','cancelling') AND finished_at IS NULL) OR (status IN ('succeeded','failed','cancelled','interrupted') AND finished_at IS NOT NULL)",
            name="finish_valid",
        ),
        CheckConstraint("model_calls >= 0 AND skill_reads >= 0", name="budgets_valid"),
        CheckConstraint("revision > 0 AND actions_revision > 0", name="revision_valid"),
        CheckConstraint(
            "json_valid(config_snapshot) AND json_type(config_snapshot) = 'object'",
            name="snapshot_valid",
        ),
        CheckConstraint(
            "json_valid(input_snapshot) AND json_type(input_snapshot) = 'array'", name="input_valid"
        ),
        CheckConstraint("usage IS NULL OR json_valid(usage)", name="usage_valid"),
        Index("ix_runs_status_created", "status", "created_at", "id"),
        Index(
            "uq_runs_thread_active",
            "thread_id",
            unique=True,
            sqlite_where=text(
                "thread_id IS NOT NULL AND status IN ('queued','running','cancelling')"
            ),
        ),
    )
    agent_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("agents.id"))
    owner_user_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("users.id"), index=True)
    initiated_by_user_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("users.id"))
    initiated_by_session_id: Mapped[str | None] = mapped_column(
        UUIDText(), ForeignKey("auth_sessions.id", ondelete="SET NULL"), index=True
    )
    origin_kind: Mapped[str] = mapped_column(Text)
    operation: Mapped[str] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(Text, default="user")
    mode: Mapped[str] = mapped_column(Text, default="execute")
    client_request_id: Mapped[str] = mapped_column(UUIDText())
    request_hash: Mapped[str] = mapped_column(Text)
    retry_of_run_id: Mapped[str | None] = mapped_column(NumericID())
    model_connection_id: Mapped[str | None] = mapped_column(
        UUIDText(), ForeignKey("model_connections.id", ondelete="SET NULL"), index=True
    )
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    input_snapshot: Mapped[list] = mapped_column(JSON)
    thread_id: Mapped[str] = mapped_column(Text)
    base_checkpoint_id: Mapped[str | None] = mapped_column(Text)
    base_run_id: Mapped[str | None] = mapped_column(NumericID(), ForeignKey("runs.id"))
    checkpoint_id: Mapped[str | None] = mapped_column(Text)
    result_text: Mapped[str | None] = mapped_column(Text)
    result_data: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    actions_revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    model_calls: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    skill_reads: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    tool_calls: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(Text)
    usage: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    cancel_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class RunAction(IdentityTimestamps, Base):
    __tablename__ = "run_actions"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_run_actions_sequence"),
        UniqueConstraint("run_id", "action_key", name="uq_run_actions_key"),
        Index("ix_run_actions_call", "run_id", "call_key"),
        CheckConstraint("sequence > 0", name="sequence_positive"),
        CheckConstraint("length(trim(action_key)) > 0", name="key_valid"),
        CheckConstraint(
            "kind IN ('skill_activation','model_call','tool_call','knowledge','validation')",
            name="kind_valid",
        ),
        CheckConstraint(
            "status IN ('running','succeeded','failed','cancelled','interrupted','unknown')",
            name="status_valid",
        ),
        CheckConstraint(
            "(status = 'running' AND finished_at IS NULL) OR (status != 'running' AND finished_at IS NOT NULL)",
            name="finish_valid",
        ),
        CheckConstraint(
            "json_valid(safe_details) AND json_type(safe_details) = 'object'", name="details_valid"
        ),
        CheckConstraint("reasoning_truncated IN (0, 1)", name="reasoning_boolean"),
    )
    run_id: Mapped[str] = mapped_column(NumericID(), ForeignKey("runs.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    action_key: Mapped[str] = mapped_column(Text)
    call_key: Mapped[str] = mapped_column(
        Text, default=lambda context: context.get_current_parameters()["action_key"]
    )
    parent_action_id: Mapped[str | None] = mapped_column(UUIDText(), ForeignKey("run_actions.id"))
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="running")
    skill_id: Mapped[str | None] = mapped_column(
        UUIDText(), ForeignKey("skills.id", ondelete="SET NULL")
    )
    safe_details: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    output_text: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    reasoning_text: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    reasoning_truncated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0")
    )
    result_ref: Mapped[str | None] = mapped_column(Text)
    result_payload: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    request_file_id: Mapped[str | None] = mapped_column(UUIDText(), ForeignKey("stored_files.id"))
    response_file_id: Mapped[str | None] = mapped_column(UUIDText(), ForeignKey("stored_files.id"))
    error_code: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
