"""Product communication and its explicit execution bindings."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import (
    NumericID,
    NumericIdentityTimestamps,
    UTCDateTime,
    UUIDText,
)


class Conversation(NumericIdentityTimestamps, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("id BETWEEN 100000000000 AND 999999999999", name="numeric_id_range"),
        CheckConstraint("length(title) BETWEEN 1 AND 100", name="title_length"),
        CheckConstraint("last_message_sequence >= 0", name="sequence_valid"),
        CheckConstraint("revision > 0", name="revision_valid"),
        Index("ix_conversations_updated", "updated_at", "id"),
        Index("ix_conversations_agent_updated", "agent_id", "updated_at", "id"),
    )
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    agent_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("agents.id"))
    owner_user_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(Text, default="新对话")
    last_message_sequence: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class Message(NumericIdentityTimestamps, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("id BETWEEN 100000000000 AND 999999999999", name="numeric_id_range"),
        UniqueConstraint("conversation_id", "id", name="uq_messages_identity"),
        UniqueConstraint("conversation_id", "sequence", name="uq_messages_sequence"),
        CheckConstraint("sequence > 0", name="sequence_valid"),
        CheckConstraint(
            "(role = 'user' AND body IS NOT NULL AND length(trim(body)) > 0) OR role = 'assistant'",
            name="content_owner",
        ),
    )
    conversation_id: Mapped[str] = mapped_column(NumericID(), ForeignKey("conversations.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)

    @validates("body")
    def immutable_body(self, key, value):
        if inspect(self).persistent and self.body is not None and self.body != value:
            raise ValueError("已交付正文不可覆盖。")
        return value

    @validates("conversation_id", "sequence", "role")
    def immutable_content(self, key, value):
        if inspect(self).persistent and getattr(self, key) != value:
            raise ValueError("已保存消息不可修改。")
        return value


class ConversationRun(Base):
    __tablename__ = "conversation_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "input_message_id"], ["messages.conversation_id", "messages.id"]
        ),
        ForeignKeyConstraint(
            ["conversation_id", "run_id"], ["messages.conversation_id", "messages.id"]
        ),
        CheckConstraint("run_id != input_message_id", name="messages_distinct"),
        CheckConstraint("active IN (0,1)", name="active_valid"),
        Index(
            "uq_conversation_runs_active",
            "conversation_id",
            unique=True,
            sqlite_where=text("active = 1"),
        ),
    )
    run_id: Mapped[str] = mapped_column(NumericID(), ForeignKey("runs.id"), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(NumericID(), ForeignKey("conversations.id"))
    input_message_id: Mapped[str] = mapped_column(NumericID())
    handled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    acceptance_error: Mapped[str | None] = mapped_column(Text)
    acceptance_attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    next_acceptance_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class MessageFile(Base):
    __tablename__ = "message_files"
    message_id: Mapped[str] = mapped_column(
        NumericID(), ForeignKey("messages.id"), primary_key=True
    )
    file_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("stored_files.id"), primary_key=True
    )
