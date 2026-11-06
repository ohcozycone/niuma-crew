"""Register HTTP route groups exposed by this backend."""

from fastapi import APIRouter

from app.api.errors import SERVICE_ERROR_RESPONSES
from app.api.routes import (
    auth,
    capabilities,
    configuration_summary,
    conversations,
    employees,
    evaluations,
    files,
    health,
    knowledge,
    mcp,
    mcp_oauth,
    model_connections,
    organization_rules,
    public,
    skills,
)

router = APIRouter(responses=SERVICE_ERROR_RESPONSES)
router.include_router(health.router)
router.include_router(knowledge.router)
router.include_router(files.router)
router.include_router(configuration_summary.router)
router.include_router(auth.router)
router.include_router(public.router)
router.include_router(employees.router)
router.include_router(evaluations.router)
router.include_router(skills.router)
router.include_router(mcp.router)
router.include_router(mcp_oauth.router)
router.include_router(model_connections.router)
router.include_router(conversations.router)
router.include_router(capabilities.router)
router.include_router(organization_rules.router)
