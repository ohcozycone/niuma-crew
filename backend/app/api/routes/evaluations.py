from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import (
    ActorDependency,
    EvaluationCommandsDependency,
    EvaluationQueriesDependency,
    require_capability,
)
from app.applications.evaluations.benchmark import catalog
from app.applications.evaluations.schemas import EvaluationCreate
from app.common.schemas import RecordID

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.get("/suites", dependencies=[Depends(require_capability("runs:read"))])
def suites() -> list[dict]:
    return catalog()


@router.post("", status_code=202)
def create(
    data: EvaluationCreate, actor: ActorDependency, evaluations: EvaluationCommandsDependency
) -> dict:
    return evaluations.create(
        actor, str(data.agent_id), data.suite_id, data.sample_count, str(data.client_request_id)
    )


@router.get("")
def listing(
    actor: ActorDependency,
    evaluations: EvaluationQueriesDependency,
    agent_id: UUID,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    return evaluations.list(actor, str(agent_id), offset, limit)


@router.get("/{batch_id}")
def read(
    batch_id: RecordID,
    actor: ActorDependency,
    evaluations: EvaluationQueriesDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    return evaluations.read(actor, batch_id, offset, limit)


@router.post("/{batch_id}/cancel")
def cancel(
    batch_id: RecordID, actor: ActorDependency, evaluations: EvaluationCommandsDependency
) -> dict:
    return evaluations.cancel(actor, batch_id)


@router.get("/{batch_id}/cases/{case_id}/trace")
def execution_trace(
    batch_id: RecordID,
    case_id: UUID,
    actor: ActorDependency,
    evaluations: EvaluationQueriesDependency,
    response: Response,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    action_id: UUID | None = None,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return evaluations.trace(
        actor,
        batch_id,
        str(case_id),
        offset=offset,
        limit=limit,
        action_id=str(action_id) if action_id else None,
    )


@router.get("/{batch_id}/cases/{case_id}/trace/actions/{action_id}/evidence/{direction}")
def execution_evidence(
    batch_id: RecordID,
    case_id: UUID,
    actor: ActorDependency,
    evaluations: EvaluationQueriesDependency,
    action_id: UUID,
    direction: str,
) -> Response:
    return Response(
        evaluations.trace_evidence(actor, batch_id, str(case_id), str(action_id), direction),
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="execution-evidence.json"',
            "X-Content-Type-Options": "nosniff",
        },
    )
