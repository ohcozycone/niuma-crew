"""Process liveness endpoint."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import __version__
from app.api.dependencies import ExecutionStatusDependency

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report process liveness, not downstream dependency readiness."""
    return HealthResponse(status="ok", service="backend", version=__version__)


@router.get(
    "/ready", response_model=ReadinessResponse, responses={503: {"model": ReadinessResponse}}
)
async def ready(status: ExecutionStatusDependency):
    return JSONResponse({"status": status.phase}, status_code=200 if status.accepting else 503)
