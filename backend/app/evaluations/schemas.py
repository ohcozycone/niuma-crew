"""Assessment commands; hidden expected answers are never execution inputs."""

from uuid import UUID

from pydantic import Field

from app.schemas import RequestModel


class EvaluationCreate(RequestModel):
    agent_id: UUID
    suite_id: str = "bfcl-v4-simple-python"
    sample_count: int = Field(default=5, ge=1, le=400, strict=True)
    client_request_id: UUID
