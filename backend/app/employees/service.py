"""Agent CRUD and transactional updates to the current capability assignments."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.conversations.models import Conversation
from app.employees.access import edit_agent
from app.employees.models import Agent, AgentSkill, AgentToolGrant
from app.employees.schemas import (
    AgentCreate,
    AgentPatch,
    AgentRead,
    AgentResourceCounts,
    AgentSkillSummary,
    AgentSummary,
    AgentUsage,
    PublicAgent,
    SkillAssignmentRead,
    UsageSkill,
)
from app.employees.tool_grants import apply_grants, grant_count, grant_read, grants_for
from app.errors import ConflictError, InvalidInputError, NotFoundError
from app.infrastructure.database.errors import is_unique_violation
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.model_connections.models import ModelConnection
from app.schemas import Page
from app.skills.definitions import definition_from_record, readiness_reason
from app.skills.models import Skill
from app.skills.parameters import validate_parameters
from app.values import utc_now


def require_agent(session: Session, agent_id: str) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise NotFoundError("agent_not_found", "员工不存在。")
    return agent


def validate_model_binding(session: Session, connection_id) -> None:
    if connection_id is None:
        return
    connection = session.get(ModelConnection, str(connection_id))
    if connection is None:
        raise NotFoundError("model_connection_not_found", "所选大脑不存在，请刷新后重新选择。")
    if not connection.enabled or connection.capability != "chat":
        raise ConflictError("model_not_configured", "所选大脑未启用或不支持聊天，请重新选择。")


def agent_conflict(error: IntegrityError) -> ConflictError | None:
    if is_unique_violation(error, table="agents", columns=("name",)):
        return ConflictError("agent_name_conflict", "员工名称已存在，请换个名字。")
    if is_unique_violation(error, table="agents", columns=("code",)):
        return ConflictError("agent_code_conflict", "员工编号已存在。")
    return None


def validate_agent_name(session: Session, name: str, *, agent_id: str | None = None) -> None:
    query = select(Agent.id).where(Agent.name == name)
    if agent_id is not None:
        query = query.where(Agent.id != agent_id)
    if session.scalar(query.limit(1)) is not None:
        raise ConflictError("agent_name_conflict", "员工名称已存在，请换个名字。")


def assignments(session, agent_id):
    return list(
        session.scalars(
            select(AgentSkill).where(AgentSkill.agent_id == agent_id).order_by(AgentSkill.skill_id)
        )
    )


def skill_readiness(enabled: bool, skill: Skill) -> str | None:
    if not enabled:
        return "装配已停用"
    return readiness_reason(definition_from_record(skill))


def agent_response(session, agent):
    result = AgentRead.model_validate(agent)
    values = []
    for assignment in assignments(session, agent.id):
        skill = session.get(Skill, assignment.skill_id)
        reason = skill_readiness(assignment.enabled, skill)
        values.append(
            SkillAssignmentRead(
                skill_id=skill.id,
                name=skill.name,
                enabled=assignment.enabled,
                parameters=assignment.parameters,
                revision=assignment.revision,
                updated_at=assignment.updated_at,
                ready=reason is None,
                readiness_reason=reason,
            )
        )
    return result.model_copy(
        update={
            "skill_assignments": values,
            "tool_grants": [grant_read(row) for row in grants_for(session, agent.id)],
            "resource_counts": AgentResourceCounts(
                skills=sum(item.enabled for item in values),
                tools=grant_count(session, agent.id),
            ),
        }
    )


def replace_assignments(session, agent, requested):
    desired = {str(item["skill_id"]): item for item in requested}
    if len(desired) != len(requested):
        raise InvalidInputError("duplicate_skill_assignment", "每位员工只能装配同一技能一次。")
    existing = {a.skill_id: a for a in assignments(session, agent.id)}
    for skill_id, data in desired.items():
        skill = session.get(Skill, skill_id)
        if skill is None:
            raise NotFoundError("skill_not_found", "待装配技能不存在。")
        validate_parameters(skill.configuration_schema, data["parameters"])
        prior = existing.get(skill_id)
        if prior is None:
            session.add(
                AgentSkill(
                    agent_id=agent.id,
                    skill_id=skill_id,
                    enabled=data["enabled"],
                    parameters=data["parameters"],
                    revision=agent.revision,
                )
            )
        elif prior.enabled != data["enabled"] or prior.parameters != data["parameters"]:
            prior.enabled, prior.parameters = data["enabled"], data["parameters"]
            prior.revision += 1
            prior.updated_at = utc_now()
    for skill_id in existing.keys() - desired.keys():
        session.delete(existing[skill_id])


class AgentService:
    def __init__(self, database: Database):
        self.database = database

    def create(self, data: AgentCreate, actor: Actor) -> AgentRead:
        self._require_write(actor, data, "agents:create")
        user_id = actor.user_id
        try:
            with self.database.transaction() as session:
                reserve_writer(session, Agent.__table__)
                validate_agent_name(session, data.name)
                validate_model_binding(session, data.model_connection_id)
                agent = Agent(
                    revision=1,
                    created_by_user_id=user_id,
                    **data.model_dump(mode="json", exclude={"skill_assignments", "tool_grants"}),
                )
                session.add(agent)
                session.flush()
                replace_assignments(
                    session, agent, [a.model_dump(mode="json") for a in data.skill_assignments]
                )
                if data.tool_grants:
                    apply_grants(session, agent, data.tool_grants, user_id)
                session.flush()
                result = agent_response(session, agent)
            return result
        except IntegrityError as error:
            if conflict := agent_conflict(error):
                raise conflict from error
            raise

    @staticmethod
    def _require_write(actor: Actor, data: AgentCreate | AgentPatch, permission: str) -> None:
        require_permission(actor, permission)
        if "model_connection_id" in data.model_fields_set:
            require_permission(actor, "agents:assign_model")
        if "skill_assignments" in data.model_fields_set:
            require_permission(actor, "agents:assign_skills")

    def get_public(self, agent_id: str, actor: Actor) -> PublicAgent:
        """Read display fields without loading private instructions or account bindings."""
        require_permission(actor, "agents:read_public")
        with self.database.transaction() as session:
            agent = session.scalar(
                select(Agent).options(defer(Agent.system_prompt)).where(Agent.id == agent_id)
            )
            if agent is None:
                raise NotFoundError("agent_not_found", "员工不存在。")
            enabled_ids = list(
                session.scalars(
                    select(AgentSkill.skill_id)
                    .where(AgentSkill.agent_id == agent.id, AgentSkill.enabled.is_(True))
                    .order_by(AgentSkill.skill_id)
                )
            )
            fields = {
                name: getattr(agent, name)
                for name in PublicAgent.model_fields
                if name not in {"skill_ids", "resource_counts", "model_configured"}
            }
            return PublicAgent(
                **fields,
                skill_ids=enabled_ids,
                model_configured=bool(agent.model_connection_id),
                resource_counts=AgentResourceCounts(
                    skills=len(enabled_ids),
                    tools=(
                        session.scalar(
                            select(
                                func.coalesce(
                                    func.sum(func.json_array_length(AgentToolGrant.tools)), 0
                                )
                            ).where(
                                AgentToolGrant.agent_id == agent.id,
                                AgentToolGrant.enabled.is_(True),
                            )
                        )
                        or 0
                    ),
                ),
            )

    def get_usage(self, agent_id: str, actor: Actor) -> AgentUsage:
        """Project only the configuration required by the conversation composer."""
        require_permission(actor, "runs:create")
        with self.database.transaction() as session:
            agent = session.scalar(
                select(Agent).options(defer(Agent.system_prompt)).where(Agent.id == agent_id)
            )
            if agent is None:
                raise NotFoundError("agent_not_found", "员工不存在。")
            values = []
            rows = session.execute(
                select(AgentSkill.enabled, Skill)
                .join(Skill, Skill.id == AgentSkill.skill_id)
                .where(AgentSkill.agent_id == agent.id)
                .order_by(AgentSkill.skill_id)
            )
            for enabled, skill in rows:
                reason = skill_readiness(enabled, skill)
                values.append(
                    UsageSkill(
                        skill_id=skill.id,
                        name=skill.name,
                        enabled=enabled,
                        ready=reason is None,
                        readiness_reason=reason,
                    )
                )
            return AgentUsage.model_validate(
                {
                    **{
                        name: getattr(agent, name)
                        for name in (
                            "id",
                            "name",
                            "description",
                            "avatar_id",
                            "is_active",
                            "example_tasks",
                        )
                    },
                    "model_configured": bool(agent.model_connection_id),
                    "skill_assignments": values,
                }
            )

    def get(self, agent_id: str, actor: Actor) -> AgentRead:
        require_permission(actor, "agents:read")
        with self.database.transaction() as session:
            agent = require_agent(session, agent_id)
            return agent_response(session, agent)

    def list(
        self,
        *,
        actor: Actor,
        offset: int = 0,
        limit: int = 20,
        q: str = "",
        category: str | None = None,
        is_active: bool | None = None,
        is_favorite: bool | None = None,
        skill_id: str | None = None,
        model_configured: bool | None = None,
        summary: bool = True,
    ) -> Page[AgentSummary | PublicAgent]:
        require_permission(actor, "agents:read" if summary else "agents:read_public")
        conditions = []
        if q.strip():
            conditions.append(
                or_(
                    Agent.name.icontains(q.strip(), autoescape=True),
                    Agent.description.icontains(q.strip(), autoescape=True),
                    Agent.role_label.icontains(q.strip(), autoescape=True),
                    Agent.code.icontains(q.strip(), autoescape=True),
                    Agent.id.in_(
                        select(AgentSkill.agent_id)
                        .join(Skill)
                        .where(Skill.name.icontains(q.strip(), autoescape=True))
                    ),
                )
            )
        if model_configured is not None:
            configured = Agent.model_connection_id.in_(
                select(ModelConnection.id).where(
                    ModelConnection.enabled.is_(True), ModelConnection.capability == "chat"
                )
            )
            conditions.append(configured if model_configured else ~configured)
        if category is not None:
            conditions.append(Agent.category == category)
        if is_active is not None:
            conditions.append(Agent.is_active == is_active)
        if is_favorite is not None:
            conditions.append(Agent.is_favorite == is_favorite)
        if skill_id is not None:
            conditions.append(
                Agent.id.in_(select(AgentSkill.agent_id).where(AgentSkill.skill_id == skill_id))
            )
        with self.database.transaction() as session:
            total = session.scalar(select(func.count()).select_from(Agent).where(*conditions))
            tool_total = (
                select(func.coalesce(func.sum(func.json_array_length(AgentToolGrant.tools)), 0))
                .where(AgentToolGrant.agent_id == Agent.id, AgentToolGrant.enabled.is_(True))
                .correlate(Agent)
                .scalar_subquery()
            )
            agent_rows = list(
                session.execute(
                    select(Agent, tool_total)
                    .options(
                        defer(Agent.system_prompt),
                        *(
                            [defer(Agent.example_tasks), defer(Agent.deliverables)]
                            if summary
                            else []
                        ),
                    )
                    .where(*conditions)
                    .order_by(Agent.created_at.desc(), Agent.id)
                    .offset(offset)
                    .limit(limit)
                )
            )
            agents = [row[0] for row in agent_rows]
            tool_counts = {row[0].id: row[1] for row in agent_rows}
            grouped = {agent.id: [] for agent in agents}
            if grouped:
                for agent_id, skill_id, enabled, name in session.execute(
                    select(
                        AgentSkill.agent_id,
                        AgentSkill.skill_id,
                        AgentSkill.enabled,
                        Skill.name,
                    )
                    .join(Skill)
                    .where(AgentSkill.agent_id.in_(grouped))
                    .order_by(AgentSkill.skill_id)
                ):
                    grouped[agent_id].append(
                        AgentSkillSummary(skill_id=skill_id, name=name, enabled=enabled)
                    )
            items = []
            for agent in agents:
                values = grouped[agent.id]
                counts = AgentResourceCounts(
                    skills=sum(a.enabled for a in values),
                    tools=tool_counts[agent.id],
                )
                if summary:
                    items.append(
                        AgentSummary.model_validate(agent).model_copy(
                            update={"skill_summaries": values, "resource_counts": counts}
                        )
                    )
                else:
                    public_fields = {
                        name: getattr(agent, name)
                        for name in PublicAgent.model_fields
                        if name not in ("skill_ids", "resource_counts", "model_configured")
                    }
                    items.append(
                        PublicAgent(
                            **public_fields,
                            skill_ids=[a.skill_id for a in values if a.enabled],
                            resource_counts=counts,
                            model_configured=bool(agent.model_connection_id),
                        )
                    )
            return Page(items=items, total=total, offset=offset, limit=limit)

    def update(self, agent_id: str, data: AgentPatch, actor: Actor) -> AgentRead:
        self._require_write(actor, data, "agents:update")
        user_id = actor.user_id
        try:
            with self.database.transaction() as session:
                reserve_writer(session, Agent.__table__)
                agent = require_agent(session, agent_id)
                edit_agent(agent, actor.user_id, admin=actor.role == "admin")
                if agent.revision != data.expected_revision:
                    raise ConflictError(
                        "configuration_revision_conflict",
                        "员工配置已被修改，请刷新后核对；当前草稿已保留。",
                    )
                changes = data.model_dump(
                    mode="json", exclude_unset=True, exclude={"expected_revision", "tool_grants"}
                )
                if "name" in changes:
                    validate_agent_name(session, changes["name"], agent_id=agent.id)
                requested_skills = changes.pop("skill_assignments", None)
                if requested_skills is not None:
                    requested_skills = [a.model_dump(mode="json") for a in data.skill_assignments]
                changed = "tool_grants" in data.model_fields_set or any(
                    getattr(agent, key) != value for key, value in changes.items()
                )
                if requested_skills is not None:
                    current = {
                        a.skill_id: (a.enabled, a.parameters)
                        for a in assignments(session, agent.id)
                    }
                    desired = {
                        a["skill_id"]: (a["enabled"], a["parameters"]) for a in requested_skills
                    }
                    changed |= current != desired
                if changed:
                    agent.revision += 1
                    agent.updated_at = utc_now()
                if "model_connection_id" in changes:
                    validate_model_binding(session, changes["model_connection_id"])
                for key, value in changes.items():
                    setattr(agent, key, value)
                if requested_skills is not None:
                    replace_assignments(session, agent, requested_skills)
                if "tool_grants" in data.model_fields_set:
                    apply_grants(session, agent, data.tool_grants, user_id)
                session.flush()
                result = agent_response(session, agent)
            return result
        except IntegrityError as error:
            if conflict := agent_conflict(error):
                raise conflict from error
            raise

    def delete(self, agent_id: str, actor: Actor) -> None:
        require_permission(actor, "agents:delete")
        with self.database.transaction() as session:
            reserve_writer(session, Agent.__table__)
            agent = require_agent(session, agent_id)
            edit_agent(agent, actor.user_id, admin=actor.role == "admin")
            from app.evaluations.models import EvaluationBatch

            if session.scalar(
                select(EvaluationBatch.id).where(EvaluationBatch.agent_id == agent_id).limit(1)
            ):
                raise ConflictError("agent_has_evaluations", "员工已有考核记录，请改为停用。")
            if session.scalar(
                select(Conversation.id).where(Conversation.agent_id == agent_id).limit(1)
            ):
                raise ConflictError("agent_has_conversations", "员工已有对话历史，请改为停用。")
            session.delete(agent)
            session.flush()
