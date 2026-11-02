"""Capture employee configuration and recheck its current assembly for execution."""

import json
from collections.abc import Collection, Iterable, Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.models import Agent, AgentSkill
from app.errors import ConflictError, InvalidInputError, NotFoundError
from app.skills.contracts import SkillExecutionEntry
from app.skills.definitions import definition_from_record, readiness_reason
from app.skills.models import Skill
from app.skills.parameters import validate_parameters


def configured_agent(db: Session, agent_id: str) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise NotFoundError("agent_not_found", "员工不存在。")
    if not agent.is_active:
        raise ConflictError("agent_inactive", "员工已停用。")
    if not agent.model_connection_id:
        raise ConflictError("model_not_configured", "请先为员工装配大脑。")
    return agent


def capture_skills(
    db: Session, agent: Agent, selected: Collection[str]
) -> list[SkillExecutionEntry]:
    rows = db.execute(
        select(AgentSkill, Skill)
        .join(Skill)
        .where(AgentSkill.agent_id == agent.id)
        .order_by(Skill.id)
    )
    candidates: list[SkillExecutionEntry] = []
    available = set()
    for relation, skill in rows:
        definition = definition_from_record(skill)
        ready = relation.enabled and readiness_reason(definition) is None
        if skill.id in selected and not ready:
            raise ConflictError("skill_not_ready", "所选技能尚未就绪。")
        if not ready:
            continue
        validate_parameters(skill.configuration_schema, relation.parameters)
        available.add(skill.id)
        candidates.append(
            SkillExecutionEntry(
                skill_id=definition.skill_id,
                name=definition.name,
                description=definition.description,
                instructions=definition.instructions,
                skill_md=definition.skill_md,
                compatibility=definition.compatibility,
                package_manifest=definition.package_manifest,
                instructions_hash=definition.instructions_hash,
                skill_revision=definition.skill_revision,
                assignment_revision=relation.revision,
                assignment_created_at=relation.created_at.isoformat(),
                parameters=relation.parameters,
            )
        )
    if set(selected) - available:
        raise ConflictError("skill_not_allowed", "所选技能不属于当前员工的可用装配。")
    if len(candidates) > 32 or len(json.dumps(candidates, ensure_ascii=False).encode()) > 262144:
        raise InvalidInputError(
            "skill_snapshot_limit", "技能快照超过 32 项或 256 KiB 上限，请精简装配。"
        )
    return candidates


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
