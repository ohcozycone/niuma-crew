from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.employees.models import Agent, AgentSkill, AgentToolGrant
from app.environments.policy import authorize_workspace_arguments
from app.errors import ConflictError, NotFoundError
from app.mcp.connections import assert_connection
from app.mcp.policy import authorize_arguments
from app.skills.models import Skill


def configured_agent(db: Session, agent_id: str) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise NotFoundError("agent_not_found", "员工不存在。")
    if not agent.is_active:
        raise ConflictError("agent_inactive", "员工已停用。")
    if not agent.model_connection_id:
        raise ConflictError("model_not_configured", "请先为员工装配大脑。")
    return agent


def authorize_execution(
    db: Session, snapshot: Mapping[str, Any], active_ids: Iterable[str]
) -> None:
    agent = db.get(Agent, snapshot["agent_id"])
    if not agent or not agent.is_active:
        raise ConflictError("agent_inactive", "员工已停用。")
    if agent.model_connection_id != snapshot["connection_id"]:
        raise ConflictError("model_configuration_changed", "员工的大脑装配已改变。")
    captured = {item["skill_id"]: item for item in snapshot["skills"]}
    for skill_id in active_ids:
        item = captured.get(skill_id)
        relation = db.get(AgentSkill, (agent.id, skill_id))
        skill = db.get(Skill, skill_id)
        if (
            not item
            or not relation
            or not relation.enabled
            or not skill
            or not skill.is_active
            or relation.revision != item["assignment_revision"]
            or relation.created_at.isoformat() != item["assignment_created_at"]
        ):
            raise ConflictError("skill_access_revoked", "技能装配或启用状态已改变，执行已停止。")


def authorize_tool(db, snapshot, invocation):
    if invocation.skill_id:
        from app.employees.access import authorize_execution

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
        binding["kind"] == "workspace"
        if result_read
        else binding["exposed_name"] != invocation.name
    ):
        raise ConflictError("tool_not_allowed", "本轮没有获得该工具许可。")
    if binding["kind"] == "workspace":
        authorize_workspace_arguments(binding, invocation.arguments)
        return binding
    assert_binding(db, snapshot, binding)
    if result_read:
        # 分页不调用上游，但仍检查来源工具当前许可并独立扣减读取预算。
        return {**binding, "recovery": "readonly", "scope_policy": {"max_calls": 32}}
    authorize_arguments(binding, invocation.arguments)
    # MCP 的默认单工具限次属于许可策略，不给其他工具附加隐式限次。
    return {**binding, "scope_policy": {"max_calls": 32, **binding["scope_policy"]}}


def assert_binding(db, snapshot, binding):
    grant = db.get(AgentToolGrant, binding["grant_id"])
    if (
        not grant
        or not grant.enabled
        or grant.agent_id != snapshot["agent_id"]
        or grant.revision != binding["grant_revision"]
    ):
        raise ConflictError("tool_access_revoked", "员工工具许可已改变。")
    if grant.tool_connection_id != binding["connection_id"]:
        raise ConflictError("tool_access_revoked", "员工工作连接已改变，请重新发送任务。")
    if binding.get("auth_required"):
        from app.mcp.connections import require_connection

        current = require_connection(db, grant.tool_connection_id)
        if (
            current.config_revision != binding["config_revision"]
            or current.credential_revision != binding["credential_revision"]
            or (current.auth_type == "oauth" and current.oauth_status == "connected")
        ):
            raise ConflictError("tool_access_revoked", "账号状态已改变，请重新发送任务。")
        return binding
    assert_connection(db, binding)
    return binding
