from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError
from app.resources.employees.models import Agent, AgentSkill, AgentToolGrant
from app.resources.employees.schemas import AgentConfiguration
from app.resources.mcp.connections import assert_connection
from app.resources.skills.definitions import published_skill


def configured_agent(db: Session, agent_id: str) -> AgentConfiguration:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise NotFoundError("agent_not_found", "员工不存在。")
    if not agent.is_active:
        raise ConflictError("agent_inactive", "员工已停用。")
    if not agent.model_connection_id:
        raise ConflictError("model_not_configured", "请先为员工装配大脑。")
    return AgentConfiguration(
        agent.id,
        agent.name,
        agent.revision,
        agent.updated_at,
        agent.system_prompt,
        agent.model_connection_id,
    )


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
        skill = published_skill(db, skill_id)
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
        from app.resources.mcp.connections import connection_fact

        current = connection_fact(db, grant.tool_connection_id)
        if (
            current.config_revision != binding["config_revision"]
            or current.credential_revision != binding["credential_revision"]
            or (current.auth_type == "oauth" and current.oauth_status == "connected")
        ):
            raise ConflictError("tool_access_revoked", "账号状态已改变，请重新发送任务。")
        return binding
    assert_connection(db, binding)
    return binding
