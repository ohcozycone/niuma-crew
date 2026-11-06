"""Generic tool administration; no product-specific workflow endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import (
    ActorDependency,
    LimiterDependency,
    McpDefinitionDependency,
    ProfileDependency,
    ToolCatalogDependency,
    ToolConnectionDependency,
    require_capability,
)
from app.mcp.schemas import (
    CatalogAnnotations,
    CatalogApprove,
    McpConfigImport,
    McpImportPreview,
    McpServiceCreate,
    McpServicePatch,
    McpServiceRead,
    ToolCapabilities,
    ToolConnectionCreate,
    ToolConnectionPatch,
    ToolConnectionRead,
)

router = APIRouter(tags=["tools"])
admin_read = [Depends(require_capability("tools:read"))]
admin_write = [Depends(require_capability("tools:update"))]


@router.get(
    "/api/tool-connections", response_model=list[ToolConnectionRead], dependencies=admin_read
)
def listing(tools: ToolConnectionDependency, actor: ActorDependency, profiles: ProfileDependency):
    return [*tools.list(actor), *profiles.list(actor)]


@router.post(
    "/api/tool-connections",
    response_model=ToolConnectionRead,
    status_code=201,
    dependencies=admin_write,
)
def create(
    data: ToolConnectionCreate,
    actor: ActorDependency,
    tools: ToolConnectionDependency,
    profiles: ProfileDependency,
):
    return profiles.create(actor, data) if data.kind == "native" else tools.create(actor, data)


@router.patch(
    "/api/tool-connections/{id}", response_model=ToolConnectionRead, dependencies=admin_write
)
def update(
    id: UUID,
    data: ToolConnectionPatch,
    tools: ToolConnectionDependency,
    actor: ActorDependency,
    profiles: ProfileDependency,
):
    owner = profiles if profiles.contains(str(id)) else tools
    return owner.update(actor, str(id), data)


@router.delete("/api/tool-connections/{id}", status_code=204, dependencies=admin_write)
def delete_connection(
    id: UUID,
    actor: ActorDependency,
    tools: ToolConnectionDependency,
    profiles: ProfileDependency,
    expected_config_revision: int = Query(gt=0),
    expected_credential_revision: int = Query(gt=0),
):
    owner = profiles if profiles.contains(str(id)) else tools
    owner.delete(actor, str(id), expected_config_revision, expected_credential_revision)
    return Response(status_code=204)


@router.post(
    "/api/tool-connections/{id}/discover",
    response_model=ToolConnectionRead,
    dependencies=admin_write,
)
async def discover(
    id: UUID, actor: ActorDependency, catalogs: ToolCatalogDependency, limiter: LimiterDependency
):
    limiter.consume(f"tool-discovery:{actor.user_id}", 5, 60)
    return await catalogs.discover(actor, str(id))


@router.post(
    "/api/tool-connections/{id}/approve",
    response_model=ToolConnectionRead,
    dependencies=admin_write,
)
def approve(
    id: UUID, data: CatalogApprove, catalogs: ToolCatalogDependency, actor: ActorDependency
):
    return catalogs.approve(actor, str(id), data)


@router.get("/api/mcp-services", response_model=list[McpServiceRead], dependencies=admin_read)
def services(actor: ActorDependency, definitions: McpDefinitionDependency):
    return definitions.list(actor)


@router.post(
    "/api/mcp-services", response_model=McpServiceRead, status_code=201, dependencies=admin_write
)
def create_service(
    data: McpServiceCreate, actor: ActorDependency, definitions: McpDefinitionDependency
):
    return definitions.create(actor, data)


@router.patch("/api/mcp-services/{id}", response_model=McpServiceRead, dependencies=admin_write)
def update_service(
    id: UUID, data: McpServicePatch, actor: ActorDependency, definitions: McpDefinitionDependency
):
    return definitions.update(actor, str(id), data)


@router.delete("/api/mcp-services/{id}", status_code=204, dependencies=admin_write)
def delete_service(
    id: UUID,
    actor: ActorDependency,
    definitions: McpDefinitionDependency,
    expected_revision: int = Query(gt=0),
) -> Response:
    definitions.delete(actor, str(id), expected_revision)
    return Response(status_code=204)


@router.post(
    "/api/mcp-config/preview",
    response_model=McpImportPreview,
    response_model_exclude_unset=True,
    dependencies=admin_write,
)
def preview_config(
    data: McpConfigImport, actor: ActorDependency, definitions: McpDefinitionDependency
):
    return definitions.import_config(actor, data)


@router.get("/api/tool-capabilities", response_model=ToolCapabilities, dependencies=admin_read)
def tool_capabilities(actor: ActorDependency, tools: ToolConnectionDependency) -> ToolCapabilities:
    return ToolCapabilities(
        stdio_enabled=tools.config.stdio_enabled,
        stdio_registration_allowed=actor.role == "admin",
        max_stdio_processes=tools.config.max_stdio_processes,
    )


@router.put(
    "/api/tool-connections/{id}/annotations",
    response_model=ToolConnectionRead,
    dependencies=admin_write,
)
def annotations(
    id: UUID, data: CatalogAnnotations, actor: ActorDependency, catalogs: ToolCatalogDependency
):
    return catalogs.annotate(actor, str(id), data)


@router.post(
    "/api/tool-connections/{id}/discard",
    response_model=ToolConnectionRead,
    dependencies=admin_write,
)
def discard(
    id: UUID, data: CatalogApprove, actor: ActorDependency, catalogs: ToolCatalogDependency
):
    return catalogs.discard(actor, str(id), data)
