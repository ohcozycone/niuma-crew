"""Read-only HTTP projection of sandbox readiness and resources."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import SandboxDependency, require_capability

router = APIRouter(tags=["sandboxes"])


class SandboxResourceRead(BaseModel):
    id: str
    run_id: str
    state: str
    expires_at: str
    cleanup_attempts: int
    error: str | None


class SandboxStatus(BaseModel):
    ready: bool
    message: str
    resources: list[SandboxResourceRead]


@router.get(
    "/api/sandbox-status",
    response_model=SandboxStatus,
    dependencies=[Depends(require_capability("tools:read"))],
)
def status(sandboxes: SandboxDependency) -> SandboxStatus:
    return SandboxStatus.model_validate(
        {**sandboxes.readiness(), "resources": sandboxes.resources()}
    )
