from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, Text, text
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.common.values import optional_text, required_text, utc_now
from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import (
    UTC_TIMESTAMP_DEFAULT,
    IdentityTimestamps,
    StringListJSON,
    UTCDateTime,
    UUIDText,
)


class Agent(IdentityTimestamps, Base):
    __tablename__ = "agents"
    __table_args__ = (
        Index("ix_agents_name", "name", unique=True),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(avatar_id)) > 0", name="avatar_id_not_blank"),
        CheckConstraint("code IS NULL OR length(trim(code)) > 0", name="code_not_blank"),
        CheckConstraint(
            "CASE WHEN json_valid(example_tasks) THEN json_type(example_tasks) = 'array' ELSE 0 END",
            name="example_tasks_array",
        ),
        CheckConstraint(
            "CASE WHEN json_valid(deliverables) THEN json_type(deliverables) = 'array' ELSE 0 END",
            name="deliverables_array",
        ),
    )

    created_by_user_id: Mapped[str | None] = mapped_column(UUIDText(), ForeignKey("users.id"))
    revision: Mapped[int] = mapped_column(
        Integer, CheckConstraint("revision > 0", name="revision_positive"), server_default="1"
    )
    code: Mapped[str | None] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, server_default="其他")
    description: Mapped[str] = mapped_column(Text, server_default=text("''"))
    role_label: Mapped[str | None] = mapped_column(Text)
    avatar_id: Mapped[str] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text, server_default=text("''"))
    model_connection_id: Mapped[str | None] = mapped_column(
        UUIDText(), ForeignKey("model_connections.id"), index=True
    )
    knowledge_mode: Mapped[str] = mapped_column(
        Text,
        CheckConstraint("knowledge_mode IN ('on_demand','always')", name="knowledge_mode_valid"),
        default="on_demand",
        server_default="on_demand",
    )
    knowledge_top_k: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("knowledge_top_k BETWEEN 1 AND 12", name="knowledge_top_k_valid"),
        default=6,
        server_default="6",
    )
    allow_web_access: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="allow_web_access_boolean"),
        default=False,
        server_default=text("0"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="is_active_boolean"), server_default=text("1")
    )
    is_favorite: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="is_favorite_boolean"), server_default=text("0")
    )
    example_tasks: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(StringListJSON()), default=list, server_default="[]"
    )
    deliverables: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(StringListJSON()), default=list, server_default="[]"
    )

    @validates("name", "avatar_id")
    def validate_required_text(self, key: str, value: str) -> str:
        return required_text(value)

    @validates("code", "role_label")
    def validate_optional_text(self, key: str, value: str | None) -> str | None:
        return optional_text(value)


class AgentSkill(Base):
    __tablename__ = "agent_skills"
    __table_args__ = (Index("ix_agent_skills_skill_id", "skill_id"),)

    agent_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey(Agent.id, ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=UTC_TIMESTAMP_DEFAULT
    )

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=UTC_TIMESTAMP_DEFAULT, onupdate=utc_now
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="enabled_boolean"), server_default="1"
    )
    parameters: Mapped[dict] = mapped_column(
        JSON,
        CheckConstraint(
            "json_valid(parameters) AND json_type(parameters) = 'object'", name="parameters_object"
        ),
        default=dict,
        server_default="{}",
    )
    revision: Mapped[int] = mapped_column(
        Integer, CheckConstraint("revision > 0", name="revision_positive"), server_default="1"
    )


class AgentKnowledgeLibrary(Base):
    __tablename__ = "agent_knowledge_libraries"

    agent_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("knowledge_bases.id", ondelete="RESTRICT"), primary_key=True
    )


class AgentToolGrant(IdentityTimestamps, Base):
    __tablename__ = "agent_tool_grants"
    __table_args__ = (
        Index("uq_agent_tool_grants_connection", "agent_id", "tool_connection_id", unique=True),
        CheckConstraint("revision > 0", name="revision_positive"),
    )
    agent_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    tool_connection_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("tool_connections.id", ondelete="RESTRICT"), index=True
    )
    tools: Mapped[list] = mapped_column(JSON, default=list)
    scope_policy: Mapped[dict] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="enabled_boolean"), default=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    granted_by_user_id: Mapped[str | None] = mapped_column(UUIDText(), ForeignKey("users.id"))
