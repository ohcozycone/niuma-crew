"""Agent HTTP endpoints; synchronous database work runs in FastAPI's worker pool."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import (
    ActorDependency,
    AgentDependency,
    ToolAccountBindingDependency,
    require_capability,
)
from app.api.errors import SERVICE_ERROR_RESPONSES
from app.employees.schemas import (
    AgentCreate,
    AgentPatch,
    AgentRead,
    AgentSummary,
    AgentUsage,
    PersonalBindingsRead,
    ToolAccountBindingInput,
)
from app.schemas import Page

router = APIRouter(prefix="/api/agents", tags=["agents"], responses=SERVICE_ERROR_RESPONSES)


@router.post(
    "",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_capability("agents:create"))],
)
def create_agent(data: AgentCreate, agents: AgentDependency, actor: ActorDependency) -> AgentRead:
    return agents.create(data, actor)


@router.get(
    "",
    response_model=Page[AgentSummary],
    dependencies=[Depends(require_capability("agents:read"))],
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
    model_configured: bool | None = None,
) -> Page[AgentSummary]:
    return agents.list(
        actor=actor,
        offset=offset,
        limit=limit,
        q=q,
        category=category,
        is_active=is_active,
        is_favorite=is_favorite,
        skill_id=str(skill_id) if skill_id is not None else None,
        model_configured=model_configured,
    )


@router.get(
    "/{agent_id}",
    response_model=AgentRead,
    dependencies=[Depends(require_capability("agents:read"))],
)
def get_agent(agent_id: UUID, agents: AgentDependency, actor: ActorDependency) -> AgentRead:
    return agents.get(str(agent_id), actor)


@router.patch(
    "/{agent_id}",
    response_model=AgentRead,
    dependencies=[Depends(require_capability("agents:update"))],
)
def update_agent(
    agent_id: UUID, data: AgentPatch, agents: AgentDependency, actor: ActorDependency
) -> AgentRead:
    return agents.update(str(agent_id), data, actor)


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_capability("agents:delete"))],
)
def delete_agent(agent_id: UUID, agents: AgentDependency, actor: ActorDependency) -> Response:
    agents.delete(str(agent_id), actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{id}/my-tool-bindings",
    response_model=PersonalBindingsRead,
    dependencies=[Depends(require_capability("tools:read"))],
)
def personal_bindings(id: UUID, actor: ActorDependency, bindings: ToolAccountBindingDependency):
    return bindings.get(str(id), actor)


@router.put(
    "/{id}/my-tool-bindings/{grant_id}",
    response_model=PersonalBindingsRead,
    dependencies=[Depends(require_capability("tools:update"))],
)
def bind_personal(
    id: UUID,
    grant_id: UUID,
    data: ToolAccountBindingInput,
    actor: ActorDependency,
    bindings: ToolAccountBindingDependency,
):
    return bindings.bind(str(id), str(grant_id), data, actor)


@router.get(
    "/{id}/usage",
    response_model=AgentUsage,
    dependencies=[Depends(require_capability("runs:create"))],
)
def agent_usage(id: UUID, agents: AgentDependency, actor: ActorDependency) -> AgentUsage:
    return agents.get_usage(str(id), actor)
