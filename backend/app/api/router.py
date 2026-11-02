"""Register HTTP route groups exposed by this backend."""

from fastapi import APIRouter

from app.api.errors import SERVICE_ERROR_RESPONSES
from app.api.routes import (
    agents,
    auth,
    capabilities,
    configuration_summary,
    conversations,
    files,
    health,
    knowledge,
    model_connections,
    organization_rules,
    public,
    sandboxes,
    skills,
    tools,
)

router = APIRouter(responses=SERVICE_ERROR_RESPONSES)
router.include_router(health.router)
router.include_router(knowledge.router)
router.include_router(files.router)
router.include_router(configuration_summary.router)
router.include_router(auth.router)
router.include_router(public.router)
router.include_router(agents.router)
router.include_router(skills.router)
router.include_router(tools.router)
router.include_router(model_connections.router)
router.include_router(conversations.router)
router.include_router(capabilities.router)
router.include_router(sandboxes.router)
router.include_router(organization_rules.router)
