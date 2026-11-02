"""Bounded read-only SSE observation; disconnects only release this subscription."""

import asyncio
import time

from fastapi.responses import StreamingResponse

from app.auth.permissions import require_permission
from app.errors import AuthenticationError, PermissionDeniedError, RateLimitError
from app.execution.models import TERMINAL


async def subscribe(id: str, response_id: str, request, actor, queries):
    await asyncio.to_thread(queries.response, actor, str(id), response_id)
    counts, settings = request.app.state.subscriptions, request.app.state.runtime_settings
    key = actor.user_id
    if counts.get(key, 0) >= settings.subscription_limit:
        raise RateLimitError("subscription_limit", "订阅过多，请关闭其他对话窗口。", retry_after=2)
    counts[key] = counts.get(key, 0) + 1
    released = False

    def release():
        nonlocal released
        if not released:
            counts[key] -= 1
            if counts[key] == 0:
                counts.pop(key)
            released = True

    async def snapshots():
        started = heartbeat = authorized = time.monotonic()
        revision = -1
        current_actor = actor
        try:
            while time.monotonic() - started < settings.subscription_seconds:
                if await request.is_disconnected():
                    break
                if time.monotonic() - authorized >= settings.auth_interval:
                    try:
                        current_actor = await asyncio.to_thread(
                            request.app.state.auth.resolve_session, actor.session_id
                        )
                        require_permission(current_actor, "runs:read")
                    except (AuthenticationError, PermissionDeniedError):
                        yield "event: access.revoked\ndata: {}\n\n"
                        return
                    authorized = time.monotonic()
                snapshot = await asyncio.to_thread(
                    queries.response, current_actor, str(id), response_id
                )
                if snapshot.response.version > revision:
                    event = (
                        "response.finished"
                        if snapshot.response.status in TERMINAL
                        else "response.snapshot"
                    )
                    yield f"id: {snapshot.response.version}\nevent: {event}\ndata: {snapshot.model_dump_json()}\n\n"
                    revision = snapshot.response.version
                if snapshot.response.status in TERMINAL:
                    break
                if time.monotonic() - heartbeat >= 15:
                    yield ": heartbeat\n\n"
                    heartbeat = time.monotonic()
                await asyncio.sleep(settings.poll_interval)
        finally:
            release()

    class SubscriptionResponse(StreamingResponse):
        async def __call__(self, scope, receive, send):
            try:
                await super().__call__(scope, receive, send)
            finally:
                # Also covers disconnects before the iterator starts or headers are sent.
                release()

    return SubscriptionResponse(
        snapshots(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
