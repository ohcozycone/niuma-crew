"""Authenticated command endpoints and bounded, read-only SSE subscriptions."""

import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.dependencies import (
    ActorDependency,
    ConversationDependency,
    ConversationQueriesDependency,
    ExecutionQueriesDependency,
)
from app.api.streaming import ResponseEventsDependency
from app.conversations.schemas import (
    AcceptedSubmission,
    ConversationRead,
    ConversationSnapshot,
    ConversationStats,
    ConversationStatusFilter,
    CreateRequest,
    EmptyRequest,
    MessagePage,
    QuestionPage,
    QuestionPreviewRead,
    ResponseSnapshot,
    RetryRequest,
    SendRequest,
)
from app.schemas import Page, RecordID

logger = logging.getLogger(__name__)
router = APIRouter(tags=["conversations"])


@router.post("/api/conversations", response_model=AcceptedSubmission, status_code=202)
def create(
    data: CreateRequest,
    actor: ActorDependency,
    commands: ConversationDependency,
    response: Response,
):
    result, created = commands.submit(
        actor,
        None,
        str(data.client_request_id),
        data.content,
        selected_skill_ids=[str(value) for value in data.selected_skill_ids],
        agent_id=str(data.agent_id),
        file_ids=[str(value) for value in data.file_ids],
    )
    response.status_code = 202 if created else 200
    logger.info(
        "submission.%s conversation=%s response=%s request=%s",
        "accepted" if created else "replayed",
        result.conversation.id,
        result.response.id,
        result.client_request_id,
    )
    return result


@router.get("/api/conversations/requests/{request_id}", response_model=AcceptedSubmission | None)
def find_creation(request_id: UUID, actor: ActorDependency, queries: ConversationQueriesDependency):
    return queries.find_request(actor, None, str(request_id))


@router.get("/api/conversations", response_model=Page[ConversationRead])
def listing(
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    agent_id: UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str, Query(max_length=200)] = "",
    status: ConversationStatusFilter | None = None,
):
    return queries.list(
        actor, str(agent_id) if agent_id else None, offset, limit, q=q, status=status
    )


@router.get("/api/conversations/stats", response_model=ConversationStats)
def statistics(
    agent_id: UUID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    response: Response,
) -> ConversationStats:
    """Read employee round totals within the caller's authorized conversation scope."""
    response.headers["Cache-Control"] = "no-store"
    return queries.stats(actor, str(agent_id))


@router.get("/api/conversations/{id}/messages", response_model=MessagePage)
def messages(
    id: RecordID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    before_sequence: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after_sequence: Annotated[int | None, Query(gt=0)] = None,
    around_message_id: RecordID | None = None,
):
    return queries.messages(
        actor,
        str(id),
        before_sequence,
        limit,
        after_sequence,
        str(around_message_id) if around_message_id else None,
    )


@router.get("/api/conversations/{id}/questions", response_model=QuestionPage)
def questions(
    id: RecordID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    after_sequence: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    q: Annotated[str, Query(max_length=200)] = "",
    anchor_message_id: RecordID | None = None,
    start_number: Annotated[int | None, Query(ge=1)] = None,
):
    return queries.questions(
        actor,
        str(id),
        after_sequence,
        limit,
        q,
        str(anchor_message_id) if anchor_message_id else None,
        start_number,
    )


@router.get(
    "/api/conversations/{id}/questions/{question_id}/preview", response_model=QuestionPreviewRead
)
def question_preview(
    id: RecordID,
    question_id: RecordID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
):
    return queries.question_preview(actor, str(id), str(question_id))


@router.post("/api/conversations/{id}/messages", response_model=AcceptedSubmission, status_code=202)
def send(
    id: RecordID,
    data: SendRequest,
    actor: ActorDependency,
    commands: ConversationDependency,
    response: Response,
):
    result, created = commands.submit(
        actor,
        str(id),
        str(data.client_request_id),
        data.content,
        selected_skill_ids=[str(value) for value in data.selected_skill_ids],
        agent_id=str(data.agent_id) if data.agent_id else None,
        file_ids=[str(value) for value in data.file_ids],
    )
    response.status_code = 202 if created else 200
    logger.info(
        "submission.%s conversation=%s response=%s request=%s",
        "accepted" if created else "replayed",
        result.conversation.id,
        result.response.id,
        result.client_request_id,
    )
    return result


@router.get(
    "/api/conversations/{id}/requests/{request_id}", response_model=AcceptedSubmission | None
)
def find_request(
    id: RecordID, request_id: UUID, actor: ActorDependency, queries: ConversationQueriesDependency
):
    return queries.find_request(actor, str(id), str(request_id))


@router.get("/api/conversations/{id}/snapshot", response_model=ConversationSnapshot)
def snapshot(
    id: RecordID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return queries.snapshot(actor, str(id), limit)


@router.get("/api/conversations/{id}/responses/{response_id}", response_model=ResponseSnapshot)
def response(
    id: RecordID,
    response_id: RecordID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
):
    return queries.response(actor, str(id), str(response_id))


@router.post(
    "/api/conversations/{id}/responses/{response_id}/stop", response_model=ResponseSnapshot
)
def stop(
    id: RecordID,
    response_id: RecordID,
    data: EmptyRequest,
    actor: ActorDependency,
    commands: ConversationDependency,
):
    return commands.cancel(actor, str(id), str(response_id))


@router.post(
    "/api/conversations/{id}/responses/{response_id}/retry", response_model=AcceptedSubmission
)
def retry(
    id: RecordID,
    response_id: RecordID,
    data: RetryRequest,
    actor: ActorDependency,
    commands: ConversationDependency,
    response: Response,
):
    result, created = commands.retry(actor, str(id), str(response_id), str(data.client_request_id))
    response.status_code = 202 if created else 200
    logger.info(
        "submission.%s conversation=%s response=%s request=%s",
        "accepted" if created else "replayed",
        result.conversation.id,
        result.response.id,
        result.client_request_id,
    )
    return result


@router.get(
    "/api/conversations/{id}/responses/{response_id}/events",
    response_class=EventSourceResponse,
)
async def events(
    subscription: ResponseEventsDependency,
) -> AsyncIterator[ServerSentEvent]:
    async for event in subscription:
        yield event


@router.get("/api/conversations/{id}/responses/{response_id}/trace")
def execution_trace(
    id: RecordID,
    response_id: RecordID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    traces: ExecutionQueriesDependency,
    response: Response,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    action_id: UUID | None = None,
) -> dict:
    run_id = queries.trace_run(actor, id, response_id)
    response.headers["Cache-Control"] = "no-store"
    result = traces.read(
        actor, run_id, offset=offset, limit=limit, action_id=str(action_id) if action_id else None
    )
    result["context"] = queries.trace_context(actor, id, run_id)
    return result


@router.get(
    "/api/conversations/{id}/responses/{response_id}/trace/actions/{action_id}/evidence/{direction}"
)
def execution_evidence(
    id: RecordID,
    response_id: RecordID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    traces: ExecutionQueriesDependency,
    action_id: UUID,
    direction: str,
) -> Response:
    run_id = queries.trace_run(actor, id, response_id)
    return Response(
        traces.download(actor, run_id, str(action_id), direction),
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="execution-evidence.json"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/conversations/{id}/trace")
def latest_execution_trace(
    id: RecordID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    traces: ExecutionQueriesDependency,
    response: Response,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    action_id: UUID | None = None,
) -> dict:
    run_id = queries.trace_run(actor, id)
    response.headers["Cache-Control"] = "no-store"
    result = traces.read(
        actor, run_id, offset=offset, limit=limit, action_id=str(action_id) if action_id else None
    )
    result["context"] = queries.trace_context(actor, id, run_id)
    return result
