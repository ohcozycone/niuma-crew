from fastapi import APIRouter, Depends

from app.api.dependencies import (
    ActorDependency,
    DatabaseDependency,
    require_capability,
)
from app.common.schemas import Page
from app.resources.capability_catalog.queries import list_capabilities
from app.resources.capability_catalog.schemas import CapabilityRead

router = APIRouter(tags=["capabilities"])


@router.get(
    "/api/capabilities",
    response_model=Page[CapabilityRead],
    dependencies=[Depends(require_capability("skills:read_public"))],
)
def listing(
    database: DatabaseDependency,
    actor: ActorDependency,
    q: str = "",
    kind: str = "all",
    offset: int = 0,
    limit: int = 20,
) -> Page[CapabilityRead]:
    return list_capabilities(
        database,
        actor,
        q=q,
        kind=kind,
        offset=offset,
        limit=limit,
    )
