"""Bounded read-only observation; FastAPI owns SSE encoding and keepalive."""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import Depends, Request, Response
from fastapi.sse import ServerSentEvent

from app.api.dependencies import ActorDependency, ConversationQueriesDependency
from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.conversations.schemas import ResponseSnapshot
from app.errors import AuthenticationError, PermissionDeniedError, RateLimitError
from app.execution.models import TERMINAL
from app.schemas import RecordID


async def subscribe(
    id: RecordID,
    response_id: RecordID,
    request: Request,
    response: Response,
    actor: ActorDependency,
    queries: ConversationQueriesDependency,
) -> AsyncIterator[AsyncIterator[ServerSentEvent]]:
    """Preflight before headers, and hold the quota until the request exits."""
    require_permission(actor, "runs:read")

    def read(current_actor: Actor) -> ResponseSnapshot:
        return queries.response(current_actor, str(id), str(response_id))

    await asyncio.to_thread(read, actor)
    counts, settings = request.app.state.subscriptions, request.app.state.runtime_settings
    key = actor.user_id
    if counts.get(key, 0) >= settings.subscription_limit:
        raise RateLimitError("subscription_limit", "订阅过多，请关闭其他对话窗口。", retry_after=2)
    counts[key] = counts.get(key, 0) + 1
    try:
        response.headers["Cache-Control"] = "no-store"
        # Also exits when streaming never starts or sending headers fails.
        yield _snapshots(request, actor, read)
    finally:
        counts[key] -= 1
        if counts[key] == 0:
            counts.pop(key)


ResponseEventsDependency = Annotated[
    AsyncIterator[ServerSentEvent], Depends(subscribe, scope="request")
]


async def _snapshots(
    request: Request, actor: Actor, read: Callable[[Actor], ResponseSnapshot]
) -> AsyncIterator[ServerSentEvent]:
    settings = request.app.state.runtime_settings
    started = authorized = time.monotonic()
    revision = -1
    current_actor = actor
    while time.monotonic() - started < settings.subscription_seconds:
        if time.monotonic() - authorized >= settings.auth_interval:
            try:
                current_actor = await asyncio.to_thread(
                    request.app.state.auth.resolve_session, actor.session_id
                )
                require_permission(current_actor, "runs:read")
            except (AuthenticationError, PermissionDeniedError):
                yield ServerSentEvent(event="access.revoked", data={})
                return
            authorized = time.monotonic()
        try:
            snapshot = await asyncio.to_thread(read, current_actor)
        except (AuthenticationError, PermissionDeniedError):
            yield ServerSentEvent(event="access.revoked", data={})
            return
        version = snapshot.response.version
        finished = (
            snapshot.response.status in TERMINAL and snapshot.response.acceptance != "pending"
        )
        if version > revision:
            event = "response.finished" if finished else "response.snapshot"
            yield ServerSentEvent(id=str(version), event=event, data=snapshot)
            revision = version
        if finished:
            return
        await asyncio.sleep(settings.poll_interval)
