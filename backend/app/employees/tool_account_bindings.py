"""User account bindings never modify shared employee instructions or permissions."""

from __future__ import annotations

from sqlalchemy import select

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.employees.models import AgentToolGrant, PersonalToolBinding
from app.employees.schemas import ToolAccountBindingInput
from app.employees.service import require_agent
from app.employees.tool_grants import grants_for
from app.errors import ConflictError, InvalidInputError, NotFoundError
from app.infrastructure.database.transactions import reserve_writer
from app.mcp.access import own_connection
from app.mcp.connections import require_connection
from app.mcp.models import McpService


class ToolAccountBindingService:
    def __init__(self, database):
        self.database = database

    def get(self, agent_id: str, actor: Actor):
        require_permission(actor, "tools:read")
        user_id = actor.user_id
        with self.database.transaction() as db:
            require_agent(db, agent_id)
            result = []
            for grant in grants_for(db, agent_id):
                if not grant.enabled:
                    continue
                template = require_connection(db, grant.tool_connection_id)
                if template.kind not in {"mcp_http", "mcp_stdio"}:
                    continue
                resolved, binding = resolve_account(db, grant, user_id)
                result.append(
                    dict(
                        grant_id=grant.id,
                        service_id=template.service_id,
                        service_name=db.get(McpService, template.service_id).name,
                        account_mode=grant.account_mode,
                        creator_default=template.created_by_user_id == user_id,
                        tools=grant.tools,
                        connection_id=resolved.id
                        if resolved and resolved.created_by_user_id == user_id
                        else None,
                        connected=resolved is not None,
                        revision=binding.revision if binding else 0,
                    )
                )
            return {"items": result}

    def bind(self, agent_id: str, grant_id: str, data: ToolAccountBindingInput, actor: Actor):
        require_permission(actor, "tools:update")
        user_id = actor.user_id
        with self.database.transaction() as db:
            reserve_writer(db, PersonalToolBinding.__table__)
            grant = db.get(AgentToolGrant, grant_id)
            if not grant or grant.agent_id != agent_id or not grant.enabled:
                raise NotFoundError("tool_grant_not_found", "员工操作许可不存在。")
            if grant.account_mode != "personal":
                raise InvalidInputError("tool_binding_invalid", "共用账号由员工创建者管理。")
            template = require_connection(db, grant.tool_connection_id)
            binding = db.scalar(
                select(PersonalToolBinding).where(
                    PersonalToolBinding.user_id == user_id, PersonalToolBinding.grant_id == grant_id
                )
            )
            if (binding.revision if binding else 0) != data.expected_revision:
                raise ConflictError("tool_binding_changed", "个人连接已修改，请刷新。")
            if data.connection_id is None:
                if binding:
                    db.delete(binding)
            else:
                connection = own_connection(db, data.connection_id, user_id)
                catalog = {
                    item["name"]: item["descriptor_hash"] for item in connection.approved_catalog
                }
                if (
                    connection.service_id != template.service_id
                    or not connection.enabled
                    or any(
                        catalog.get(item["name"]) != item["descriptor_hash"] for item in grant.tools
                    )
                ):
                    raise ConflictError(
                        "tool_binding_incompatible",
                        "请选择同一服务、已确认且工具定义与员工一致的本人连接。",
                    )
                if binding:
                    binding.connection_id = connection.id
                    binding.revision += 1
                else:
                    db.add(
                        PersonalToolBinding(
                            user_id=user_id, grant_id=grant_id, connection_id=connection.id
                        )
                    )
        return self.get(agent_id, actor)


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
