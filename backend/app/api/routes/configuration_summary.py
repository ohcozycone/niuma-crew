"""Small shell aggregates, independent of current directory pages or detail payloads."""

from fastapi import APIRouter, Depends

from app.api.dependencies import DatabaseDependency, require_capability
from app.configuration_summary import ConfigurationSummary, configuration_summary

router = APIRouter(tags=["configuration"])


@router.get(
    "/api/configuration-summary",
    response_model=ConfigurationSummary,
    dependencies=[
        Depends(require_capability("agents:read")),
        Depends(require_capability("skills:read")),
    ],
)
@router.get(
    "/api/public/configuration-summary",
    response_model=ConfigurationSummary,
    dependencies=[
        Depends(require_capability("agents:read_public")),
        Depends(require_capability("skills:read_public")),
    ],
)
def summary(database: DatabaseDependency):
    return configuration_summary(database)
