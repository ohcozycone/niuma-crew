"""Session-protected display endpoints with explicit response allowlists."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    ActorDependency,
    AgentDependency,
    SkillDependency,
    require_capability,
)
from app.employees.schemas import PublicAgent
from app.schemas import Page
from app.skills.schemas import PublicSkill

router = APIRouter(prefix="/api/public", tags=["public display"])


@router.get(
    "/agents",
    response_model=Page[PublicAgent],
    dependencies=[Depends(require_capability("agents:read_public"))],
)
def list_agents(
    agents: AgentDependency,
    actor: ActorDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    q: str = "",
    category: str | None = None,
    is_active: bool | None = None,
    is_favorite: bool | None = None,
    skill_id: UUID | None = None,
):
    page = agents.list(
        actor=actor,
        offset=offset,
        limit=limit,
        summary=False,
        q=q,
        category=category,
        is_active=is_active,
        is_favorite=is_favorite,
        skill_id=str(skill_id) if skill_id else None,
    )
    return Page[PublicAgent](
        items=page.items,
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.get(
    "/agents/{agent_id}",
    response_model=PublicAgent,
    dependencies=[Depends(require_capability("agents:read_public"))],
)
def get_agent(agent_id: UUID, agents: AgentDependency, actor: ActorDependency):
    return agents.get_public(str(agent_id), actor)


@router.get(
    "/skills",
    response_model=Page[PublicSkill],
    dependencies=[Depends(require_capability("skills:read_public"))],
)
def list_skills(
    skills: SkillDependency,
    actor: ActorDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    q: str = "",
    category: str | None = None,
):
    page = skills.list(
        actor=actor, offset=offset, limit=limit, q=q, category=category, summary=False
    )
    return Page[PublicSkill](
        items=[PublicSkill.model_validate(item) for item in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.get(
    "/skills/{skill_id}",
    response_model=PublicSkill,
    dependencies=[Depends(require_capability("skills:read_public"))],
)
def get_skill(skill_id: UUID, skills: SkillDependency, actor: ActorDependency):
    return skills.get_public(str(skill_id), actor)
