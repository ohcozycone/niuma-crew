"""Authenticated command endpoints and bounded, read-only SSE subscriptions."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.api.conversation_streaming import subscribe
from app.api.dependencies import (
    ActorDependency,
    ConversationDependency,
    ConversationQueriesDependency,
)
from app.conversations.schemas import (
    AcceptedSubmission,
    ConversationCreate,
    ConversationRead,
    ConversationSnapshot,
    EmptyRequest,
    MessagePage,
    QuestionPage,
    QuestionPreviewRead,
    ResponseSnapshot,
    RetryRequest,
    SendRequest,
)
from app.schemas import Page

logger = logging.getLogger(__name__)
router = APIRouter(tags=["conversations"])


@router.post("/api/conversations", response_model=ConversationRead, status_code=201)
def create(data: ConversationCreate, actor: ActorDependency, commands: ConversationDependency):
    return commands.create(actor, str(data.agent_id))


@router.get("/api/conversations", response_model=Page[ConversationRead])
def listing(
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    agent_id: UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return queries.list(actor, str(agent_id) if agent_id else None, offset, limit)


@router.get("/api/conversations/{id}", response_model=ConversationRead)
def get(id: UUID, actor: ActorDependency, queries: ConversationQueriesDependency):
    return queries.get(actor, str(id))


@router.get("/api/conversations/{id}/messages", response_model=MessagePage)
def messages(
    id: UUID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    before_sequence: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after_sequence: Annotated[int | None, Query(gt=0)] = None,
    around_message_id: UUID | None = None,
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
    id: UUID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    after_sequence: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    q: Annotated[str, Query(max_length=200)] = "",
    anchor_message_id: UUID | None = None,
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
    id: UUID, question_id: UUID, actor: ActorDependency, queries: ConversationQueriesDependency
):
    return queries.question_preview(actor, str(id), str(question_id))


@router.post("/api/conversations/{id}/messages", response_model=AcceptedSubmission, status_code=202)
def send(
    id: UUID,
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
    id: UUID, request_id: UUID, actor: ActorDependency, queries: ConversationQueriesDependency
):
    return queries.find_request(actor, str(id), str(request_id))


@router.get("/api/conversations/{id}/snapshot", response_model=ConversationSnapshot)
def snapshot(
    id: UUID,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return queries.snapshot(actor, str(id), limit)


@router.get("/api/conversations/{id}/responses/{response_id}", response_model=ResponseSnapshot)
def response(
    id: UUID, response_id: UUID, actor: ActorDependency, queries: ConversationQueriesDependency
):
    return queries.response(actor, str(id), str(response_id))


@router.post(
    "/api/conversations/{id}/responses/{response_id}/stop", response_model=ResponseSnapshot
)
def stop(
    id: UUID,
    response_id: UUID,
    data: EmptyRequest,
    actor: ActorDependency,
    commands: ConversationDependency,
):
    return commands.cancel(actor, str(id), str(response_id))


@router.post(
    "/api/conversations/{id}/responses/{response_id}/retry", response_model=AcceptedSubmission
)
def retry(
    id: UUID,
    response_id: UUID,
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
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def events(
    id: UUID,
    response_id: UUID,
    request: Request,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
):
    return await subscribe(str(id), str(response_id), request, actor, queries)
