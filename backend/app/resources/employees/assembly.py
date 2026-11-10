from __future__ import annotations

import json
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, InvalidInputError
from app.common.values import digest
from app.resources.employees.models import Agent, AgentSkill
from app.resources.employees.schemas import AgentConfiguration
from app.resources.employees.tool_grants import grants_for
from app.resources.mcp.connections import connection_fact
from app.resources.mcp.contracts import exposed_name
from app.resources.mcp.definitions import service_fact
from app.resources.skills.contracts import SkillExecutionEntry
from app.resources.skills.definitions import published_skill, readiness_reason
from app.resources.skills.parameters import validate_parameters


def capture_skills(
    db: Session, agent: Agent | AgentConfiguration, selected: Collection[str]
) -> list[SkillExecutionEntry]:
    rows = db.scalars(
        select(AgentSkill).where(AgentSkill.agent_id == agent.id).order_by(AgentSkill.skill_id)
    )
    candidates: list[SkillExecutionEntry] = []
    available = set()
    for relation in rows:
        definition = published_skill(db, relation.skill_id)
        if definition is None:
            continue
        skill = definition
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


def capture_tools(db, agent_id):
    bindings = []
    described_connections = set()
    resumable = True
    for grant in grants_for(db, agent_id):
        if not grant.enabled:
            continue
        connection = connection_fact(db, grant.tool_connection_id)
        pending = connection.auth_type == "oauth" and connection.oauth_status != "connected"
        if not connection.enabled:
            continue
        service = service_fact(db, connection.service_id) if connection.service_id else None
        if service is not None and not service.enabled:
            continue
        catalog = {item["name"]: item for item in connection.approved_catalog}
        for selected in grant.tools:
            item = catalog.get(selected["name"])
            if not item or item["descriptor_hash"] != selected["descriptor_hash"]:
                continue
            binding = {
                **{
                    key: item[key]
                    for key in (
                        "name",
                        "description",
                        "input_schema",
                        "descriptor_hash",
                        "recovery",
                    )
                    if key in item
                },
                "agent_id": agent_id,
                "auth_required": pending,
                "service_name": service.name if service else connection.name,
                "connection_name": connection.name,
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
                "exposed_name": exposed_name(connection.id, item["name"]),
            }
            # 远端自述不能证明无副作用，因此不自动重放外部调用。
            resumable = False
            bindings.append(binding)
            described_connections.add(connection.id)
    return bindings, resumable
