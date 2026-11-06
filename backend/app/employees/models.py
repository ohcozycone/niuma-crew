"""Agent configuration and the current skills assigned to each agent."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, Text, text
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import (
    UTC_TIMESTAMP_DEFAULT,
    IdentityTimestamps,
    StringListJSON,
    UTCDateTime,
    UUIDText,
)
from app.skills.models import Skill
from app.values import optional_text, required_text, utc_now


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
        UUIDText(), ForeignKey(Skill.id, ondelete="RESTRICT"), primary_key=True
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
    account_mode: Mapped[str] = mapped_column(Text, default="personal", server_default="personal")
    tools: Mapped[list] = mapped_column(JSON, default=list)
    scope_policy: Mapped[dict] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="enabled_boolean"), default=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    granted_by_user_id: Mapped[str | None] = mapped_column(UUIDText(), ForeignKey("users.id"))


class PersonalToolBinding(IdentityTimestamps, Base):
    __tablename__ = "personal_tool_bindings"
    __table_args__ = (Index("uq_personal_tool_binding", "user_id", "grant_id", unique=True),)
    user_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("users.id"))
    grant_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("agent_tool_grants.id", ondelete="CASCADE")
    )
    connection_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("tool_connections.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)


class OrganizationRules(Base):
    __tablename__ = "organization_rules"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("revision >= 0", name="revision_valid"),
        CheckConstraint("length(instructions) <= 20000", name="instructions_length"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    instructions: Mapped[str] = mapped_column(Text, server_default=text("''"))
    revision: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=UTC_TIMESTAMP_DEFAULT
    )
