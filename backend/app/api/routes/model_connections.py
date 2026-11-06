"""Administrator-only model settings; secrets never leave the write path."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import (
    ActorDependency,
    LimiterDependency,
    ModelConnectionDependency,
    require_capability,
)
from app.model_connections.presets import ModelPreset
from app.model_connections.schemas import (
    ConnectionCreate,
    ConnectionPatch,
    ConnectionRead,
    ConnectionTestRequest,
    ConnectionTestResult,
)
from app.schemas import Page

router = APIRouter(tags=["model-connections"])


@router.get(
    "/api/model-presets",
    response_model=list[ModelPreset],
    dependencies=[Depends(require_capability("model_connections:read"))],
)
def presets(service: ModelConnectionDependency, actor: ActorDependency):
    return service.presets(actor)


@router.get(
    "/api/model-connections",
    response_model=Page[ConnectionRead],
    dependencies=[Depends(require_capability("model_connections:read"))],
)
def list_connections(
    service: ModelConnectionDependency,
    actor: ActorDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return service.list(offset, limit, actor=actor)


@router.post(
    "/api/model-connections",
    response_model=ConnectionRead,
    status_code=201,
    dependencies=[Depends(require_capability("model_connections:create"))],
)
def create_connection(
    data: ConnectionCreate, service: ModelConnectionDependency, actor: ActorDependency
):
    return service.create(data, actor)


@router.get(
    "/api/model-connections/{connection_id}",
    response_model=ConnectionRead,
    dependencies=[Depends(require_capability("model_connections:read"))],
)
def get_connection(connection_id: UUID, service: ModelConnectionDependency, actor: ActorDependency):
    return service.get(str(connection_id), actor)


@router.patch(
    "/api/model-connections/{connection_id}",
    response_model=ConnectionRead,
    dependencies=[Depends(require_capability("model_connections:update"))],
)
def update_connection(
    connection_id: UUID,
    data: ConnectionPatch,
    service: ModelConnectionDependency,
    actor: ActorDependency,
):
    return service.update(str(connection_id), data, actor)


@router.delete(
    "/api/model-connections/{connection_id}",
    status_code=204,
    dependencies=[Depends(require_capability("model_connections:delete"))],
)
def delete_connection(
    connection_id: UUID, service: ModelConnectionDependency, actor: ActorDependency
):
    service.delete(str(connection_id), actor)
    return Response(status_code=204)


@router.post(
    "/api/model-connections/{connection_id}/test",
    response_model=ConnectionTestResult,
    dependencies=[Depends(require_capability("model_connections:test"))],
)
def test_connection(
    connection_id: UUID,
    data: ConnectionTestRequest,
    service: ModelConnectionDependency,
    limiter: LimiterDependency,
    actor: ActorDependency,
):
    limiter.consume(f"model-test:{actor.user_id}", 5, 60)
    return service.test(str(connection_id), actor)
