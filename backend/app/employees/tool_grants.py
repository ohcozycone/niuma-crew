from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, field_validator
from sqlalchemy import select

from app.employees.models import AgentToolGrant
from app.errors import ConflictError, InvalidInputError
from app.mcp.connections import require_connection
from app.mcp.models import ToolConnection
from app.mcp.policy import validate_scope
from app.schemas import RequestModel


class GrantInput(RequestModel):
    connection_id: str
    tools: list[str] = Field(max_length=128)
    expected_descriptors: dict[str, str] = Field(default_factory=dict)
    scope_policy: dict
    enabled: StrictBool = True

    @field_validator("connection_id")
    @classmethod
    def valid_connection(cls, value):
        return str(UUID(value))


class GrantRead(BaseModel):
    id: str
    connection_id: str
    tools: list[dict]
    scope_policy: dict
    enabled: bool
    revision: int


def grant_read(row):
    return {
        "id": row.id,
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
            .join(ToolConnection, ToolConnection.id == AgentToolGrant.tool_connection_id)
            .where(AgentToolGrant.agent_id == agent_id)
            .where(ToolConnection.kind != "native")
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


def apply_grants(db, agent, requested_grants, user_id):
    agent_id = agent.id
    existing = {row.tool_connection_id: row for row in grants_for(db, agent_id)}
    seen = set()
    for requested in requested_grants:
        if requested.connection_id in seen or len(requested.tools) != len(set(requested.tools)):
            raise InvalidInputError("duplicate_tool_grant", "连接和工具不能重复。")
        seen.add(requested.connection_id)
        connection = require_connection(db, requested.connection_id)
        if connection.kind == "native":
            raise InvalidInputError(
                "workspace_not_assignable", "文件与执行由平台提供，不再作为员工工具装配。"
            )
        validate_scope(requested.scope_policy, connection.kind)
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
        row.tools, row.scope_policy, row.enabled = (
            values,
            requested.scope_policy,
            requested.enabled,
        )
    for id, row in existing.items():
        if id not in seen:
            db.delete(row)
