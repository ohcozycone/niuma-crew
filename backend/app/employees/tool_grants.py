"""Employee-owned tool grants and frozen invocation identities."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, field_validator
from sqlalchemy import select

from app.employees.models import AgentToolGrant, PersonalToolBinding
from app.environments.policy import validate_workspace_scope
from app.errors import ConflictError, InvalidInputError
from app.mcp.connections import require_connection
from app.mcp.policy import validate_scope
from app.schemas import RequestModel


class GrantInput(RequestModel):
    connection_id: str
    tools: list[str] = Field(max_length=128)
    expected_descriptors: dict[str, str] = Field(default_factory=dict)
    account_mode: Literal["shared", "personal"] = "personal"
    scope_policy: dict
    enabled: StrictBool = True

    @field_validator("connection_id")
    @classmethod
    def valid_connection(cls, value):
        return str(UUID(value))


class GrantRead(BaseModel):
    id: str
    account_mode: str
    connection_id: str
    tools: list[dict]
    scope_policy: dict
    enabled: bool
    revision: int


def grant_read(row):
    return {
        "id": row.id,
        "account_mode": row.account_mode,
        "connection_id": row.tool_connection_id,
        "tools": row.tools,
        "scope_policy": row.scope_policy,
        "enabled": row.enabled,
        "revision": row.revision,
    }


def grants_for(db, agent_id):
    return list(
        db.scalars(
            select(AgentToolGrant)
            .where(AgentToolGrant.agent_id == agent_id)
            .order_by(AgentToolGrant.id)
        )
    )


def grant_count(db, agent_id):
    return sum(len(row.tools) for row in grants_for(db, agent_id) if row.enabled)


def assert_connections_unused(db, connection_ids):
    if db.scalar(
        select(AgentToolGrant.id)
        .where(AgentToolGrant.tool_connection_id.in_(connection_ids))
        .limit(1)
    ):
        raise ConflictError(
            "tool_connection_in_use", "已有员工装配此服务，请先在员工能力装配中移除，再删除。"
        )
    if db.scalar(
        select(PersonalToolBinding.id)
        .where(PersonalToolBinding.connection_id.in_(connection_ids))
        .limit(1)
    ):
        raise ConflictError("tool_connection_in_use", "此连接仍有个人绑定，请先解除绑定，再删除。")


def apply_grants(db, agent, requested_grants, user_id):
    agent_id = agent.id
    existing = {row.tool_connection_id: row for row in grants_for(db, agent_id)}
    seen = set()
    native = 0
    for requested in requested_grants:
        if requested.connection_id in seen or len(requested.tools) != len(set(requested.tools)):
            raise InvalidInputError("duplicate_tool_grant", "连接和工具不能重复。")
        seen.add(requested.connection_id)
        connection = require_connection(db, requested.connection_id)
        if connection.created_by_user_id != user_id and not (
            connection.kind == "native" and connection.account_scope == "shared"
        ):
            raise InvalidInputError(
                "tool_connection_denied", "只能装配自己管理的账号连接；个人模式不会共享此账号。"
            )
        if (
            connection.kind in {"mcp_http", "mcp_stdio"}
            and requested.account_mode == "shared"
            and connection.account_scope != "shared"
        ):
            raise InvalidInputError(
                "tool_connection_denied", "个人连接不能用作员工共用账号，请先明确创建共用连接。"
            )
        (
            validate_workspace_scope(requested.scope_policy)
            if connection.kind == "native"
            else validate_scope(requested.scope_policy, connection.kind)
        )
        catalog = {item["name"]: item for item in connection.approved_catalog}
        if set(requested.tools) - catalog.keys() or (requested.enabled and not connection.enabled):
            raise ConflictError("tool_not_approved", "工具未批准或连接尚未启用。")
        if connection.kind in {"mcp_http", "mcp_stdio"} and any(
            requested.expected_descriptors.get(name) != catalog[name]["descriptor_hash"]
            for name in requested.tools
        ):
            raise ConflictError(
                "tool_definition_changed", "工具定义已变化，请核对新定义后重新选择操作。"
            )
        native += int(requested.enabled and connection.kind == "native")
        values = [
            {"name": name, "descriptor_hash": catalog[name]["descriptor_hash"]}
            for name in requested.tools
        ]
        row = existing.get(connection.id)
        if row is None:
            row = AgentToolGrant(
                agent_id=agent_id,
                tool_connection_id=connection.id,
                granted_by_user_id=user_id,
                revision=1,
            )
            db.add(row)
        elif (row.tools, row.scope_policy, row.enabled) != (
            values,
            requested.scope_policy,
            requested.enabled,
        ):
            row.revision += 1
            row.granted_by_user_id = user_id
        if row.account_mode != requested.account_mode:
            row.revision += 1
        row.account_mode = "shared" if connection.kind == "native" else requested.account_mode
        row.tools, row.scope_policy, row.enabled = (
            values,
            requested.scope_policy,
            requested.enabled,
        )
    if native > 1:
        raise InvalidInputError(
            "workspace_connection_conflict", "每位员工最多启用一份原生工作区连接。"
        )
    for id, row in existing.items():
        if id not in seen:
            db.delete(row)
