"""Correlate HTTP responses and keep unexpected failures safe at the ASGI boundary."""

import logging
import re
import traceback
from pathlib import Path
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}", re.ASCII)


class ResponseStartedFailure(RuntimeError):
    """Signal a broken response without passing private exception values to the server."""


class FailureBoundaryMiddleware:
    """Attach a diagnostic ID and report only unclassified HTTP failures."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).getlist("x-request-id")
        request_id = (
            supplied[0] if len(supplied) == 1 and REQUEST_ID.fullmatch(supplied[0]) else uuid4().hex
        )
        scope.setdefault("state", {})["request_id"] = request_id
        response_started = False

        async def correlated_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
            return
        except Exception as error:
            # Exception text, chained causes, locals and source lines can contain
            # SQL parameters or upstream credentials. Only location frames are safe.
            frames = " <- ".join(
                f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
                for frame in traceback.extract_tb(error.__traceback__)
            )
            logger.error(
                "http.failure request_id=%s type=%s started=%s frames=%s",
                request_id,
                type(error).__name__,
                response_started,
                frames,
            )
            if not response_started:
                headers = {
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "X-Request-ID": request_id,
                }
                if scope["path"] == "/api" or scope["path"].startswith("/api/"):
                    response = JSONResponse(
                        {"detail": {"code": "internal_error", "message": "服务暂时无法完成处理。"}},
                        status_code=500,
                        headers=headers,
                    )
                else:
                    response = PlainTextResponse(
                        "服务暂时无法完成处理。", status_code=500, headers=headers
                    )
                if scope["method"] == "HEAD":
                    response.body = b""
                await response(scope, receive, correlated_send)
                return

        # Raise outside the except block: neither __context__ nor __cause__ can
        # retain the original error when Uvicorn reports a stream/background fault.
        raise ResponseStartedFailure(
            f"HTTP response interrupted; request_id={request_id}"
        ) from None
