"""Employee-owned tool grants and frozen invocation identities."""

import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator
from sqlalchemy import select

from app.agents.access import edit_agent
from app.agents.models import Agent, AgentToolGrant, PersonalToolBinding
from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.errors import ConflictError, InvalidInputError
from app.infrastructure.database.transactions import reserve_writer
from app.schemas import RequestModel
from app.tools.connections import assert_connection, require_connection
from app.tools.contracts import digest, exposed_name
from app.tools.policy import authorize_arguments, validate_scope


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


class GrantsInput(RequestModel):
    expected_revision: StrictInt = Field(gt=0)
    grants: list[GrantInput] = Field(max_length=32)


class GrantRead(BaseModel):
    id: str
    account_mode: str
    connection_id: str
    tools: list[dict]
    scope_policy: dict
    enabled: bool
    revision: int


class GrantsRead(BaseModel):
    agent_revision: int
    grants: list[GrantRead]


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


class ToolGrantService:
    def __init__(self, database):
        self.database = database

    @staticmethod
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
            raise ConflictError(
                "tool_connection_in_use", "此连接仍有个人绑定，请先解除绑定，再删除。"
            )

    def get(self, agent_id: str, actor: Actor):
        from app.agents.service import require_agent

        require_permission(actor, "agents:read")
        with self.database.transaction() as db:
            agent = require_agent(db, agent_id)
            return {
                "agent_revision": agent.revision,
                "grants": [grant_read(row) for row in grants_for(db, agent_id)],
            }

    def replace(self, agent_id: str, data: GrantsInput, actor: Actor):
        from app.agents.service import require_agent

        require_permission(actor, "tools:update")
        with self.database.transaction() as db:
            reserve_writer(db, Agent.__table__)
            agent = require_agent(db, agent_id)
            edit_agent(agent, actor.user_id, admin=actor.role == "admin")
            if agent.revision != data.expected_revision:
                raise ConflictError("agent_changed", "员工配置已改变，请刷新后重试。")
            apply_grants(db, agent, data.grants, actor.user_id)
            agent.revision += 1
            db.flush()
            return {
                "agent_revision": agent.revision,
                "grants": [grant_read(row) for row in grants_for(db, agent_id)],
            }


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


def capture_tools(db, agent_id, user_id=None):
    bindings = []
    described_connections = set()
    workspace = {"mode": "virtual"}
    resumable = True
    for grant in grants_for(db, agent_id):
        if not grant.enabled:
            continue
        template = require_connection(db, grant.tool_connection_id)
        connection, personal = resolve_account(db, grant, user_id)
        pending = connection is None
        connection = connection or template
        if not template.enabled:
            continue
        catalog = {item["name"]: item for item in connection.approved_catalog}
        for selected in grant.tools:
            item = catalog.get(selected["name"])
            if not item or item["descriptor_hash"] != selected["descriptor_hash"]:
                continue
            binding = {
                **item,
                "agent_id": agent_id,
                "account_mode": grant.account_mode,
                "user_id": user_id,
                "auth_required": pending,
                "personal_binding_id": personal.id if personal else None,
                "personal_binding_revision": personal.revision if personal else None,
                "binding_id": digest([grant.id, item["name"]]),
                "grant_id": grant.id,
                "grant_revision": grant.revision,
                "connection_id": connection.id,
                "config_revision": connection.config_revision,
                "credential_revision": connection.credential_revision,
                "catalog_revision": connection.catalog_revision,
                "kind": connection.kind,
                "server_instructions": connection.approved_instructions
                if not pending and connection.id not in described_connections
                else "",
                "instructions_hash": digest(connection.approved_instructions),
                "tool_name": item["name"],
                "scope_policy": grant.scope_policy,
                "exposed_name": item["name"]
                if connection.kind == "native"
                else exposed_name(connection.id, item["name"]),
            }
            if connection.kind == "native":
                workspace = {
                    "mode": connection.public_config.get("workspace_mode", "virtual"),
                    "connection_id": connection.id,
                }
                if binding["recovery"] == "never" or workspace["mode"] == "sandbox":
                    resumable = False
            else:
                # Remote metadata is not evidence of purity; no automatic external replay.
                resumable = False
            bindings.append(binding)
            described_connections.add(connection.id)
    if len(bindings) > 128 or len(json.dumps(bindings, ensure_ascii=False).encode()) > 262144:
        raise InvalidInputError("tool_snapshot_limit", "每轮最多装配 128 个工具。")
    return bindings, workspace, resumable


def authorize_tool(db, snapshot, invocation):
    if invocation.skill_id:
        from app.agents.execution_config import authorize_execution

        authorize_execution(db, snapshot, [invocation.skill_id])
        root = f"/skills/s-{invocation.skill_id}/"
        skill = next(item for item in snapshot["skills"] if item["skill_id"] == invocation.skill_id)
        allowed = {root + "SKILL.md"} | {
            root + item["path"] for item in skill.get("package_manifest", [])
        }
        if invocation.name != "read_file" or invocation.arguments.get("file_path") not in allowed:
            raise ConflictError("skill_not_allowed", "技能文件不属于本轮目录。")
        return {"recovery": "readonly", "scope_policy": {"max_calls": 32}}
    result_read = invocation.name == "read_tool_result" and invocation.binding_id.startswith(
        "result:"
    )
    origin_id = (
        invocation.binding_id.removeprefix("result:") if result_read else invocation.binding_id
    )
    binding = next(
        (item for item in snapshot.get("tools", []) if item["binding_id"] == origin_id),
        None,
    )
    if not binding or (
        binding["kind"] == "native" if result_read else binding["exposed_name"] != invocation.name
    ):
        raise ConflictError("tool_not_allowed", "本轮没有获得该工具许可。")
    assert_binding(db, snapshot, binding)
    if result_read:
        # Reading a previously authorized result does not call the provider.
        # It has its own bounded read budget while retaining the origin's live grant.
        return {**binding, "recovery": "readonly", "scope_policy": {"max_calls": 32}}
    authorize_arguments(binding, invocation.arguments)
    return binding


def assert_binding(db, snapshot, binding):
    grant = db.get(AgentToolGrant, binding["grant_id"])
    if (
        not grant
        or not grant.enabled
        or grant.agent_id != snapshot["agent_id"]
        or grant.revision != binding["grant_revision"]
    ):
        raise ConflictError("tool_access_revoked", "员工工具许可已改变。")
    resolved, personal = resolve_account(db, grant, snapshot.get("tool_user_id"))
    if binding.get("account_mode") != grant.account_mode or binding.get("user_id") != snapshot.get(
        "tool_user_id"
    ):
        raise ConflictError("tool_access_revoked", "工具账号依据已改变，请重新发送任务。")
    if binding.get("auth_required"):
        if resolved is not None:
            raise ConflictError("tool_access_revoked", "账号已连接，请重新发送任务以使用新连接。")
        return binding
    if (
        resolved is None
        or resolved.id != binding["connection_id"]
        or (personal.id if personal else None) != binding.get("personal_binding_id")
        or (personal.revision if personal else None) != binding.get("personal_binding_revision")
    ):
        raise ConflictError("tool_access_revoked", "个人连接已改变，请重新发送任务。")
    assert_connection(db, binding)
    return binding


def resolve_account(db, grant, user_id):
    template = require_connection(db, grant.tool_connection_id)
    if template.kind == "native":
        return template, None
    if grant.account_mode == "shared":
        return (template if template.account_scope == "shared" else None), None
    personal = (
        db.scalar(
            select(PersonalToolBinding).where(
                PersonalToolBinding.user_id == user_id, PersonalToolBinding.grant_id == grant.id
            )
        )
        if user_id
        else None
    )
    connection = (
        db.get(type(template), personal.connection_id)
        if personal
        else template
        if template.created_by_user_id == user_id
        else None
    )
    if (
        connection is None
        or connection.created_by_user_id != user_id
        or connection.service_id != template.service_id
        or not connection.enabled
        or (connection.auth_type != "none" and not connection.encrypted_credentials)
    ):
        return None, personal
    catalog = {item["name"]: item["descriptor_hash"] for item in connection.approved_catalog}
    if any(catalog.get(item["name"]) != item["descriptor_hash"] for item in grant.tools):
        return None, personal
    return connection, personal
