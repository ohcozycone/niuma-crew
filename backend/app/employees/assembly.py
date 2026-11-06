"""Capture fixed employee configuration without choosing conversation history."""

from __future__ import annotations

import json
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.employees.models import Agent, AgentSkill
from app.employees.tool_account_bindings import resolve_account
from app.employees.tool_grants import grants_for
from app.errors import ConflictError, InvalidInputError
from app.mcp.connections import require_connection
from app.mcp.contracts import exposed_name
from app.skills.contracts import SkillExecutionEntry
from app.skills.definitions import definition_from_record, readiness_reason
from app.skills.models import Skill
from app.skills.parameters import validate_parameters
from app.values import digest


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
        pending = connection is None or (
            connection.auth_type == "oauth" and connection.oauth_status != "connected"
        )
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
