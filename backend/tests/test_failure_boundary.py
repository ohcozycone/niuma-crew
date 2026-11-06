"""Unexpected failures remain diagnosable without exposing exception values."""

import asyncio
import logging
import traceback

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.background import BackgroundTask
from starlette.responses import Response

from app.api.errors import register_error_handlers
from app.api.failure_boundary import FailureBoundaryMiddleware, ResponseStartedFailure
from app.errors import ServiceError


def failure_app(error):
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(FailureBoundaryMiddleware)

    @app.api_route("/api/failure", methods=["GET", "HEAD"])
    @app.api_route("/failure", methods=["GET", "HEAD"])
    def fail():
        raise error

    return app


@pytest.mark.parametrize(
    "error", [RuntimeError("private-secret"), ServiceError("x", "private-secret")]
)
@pytest.mark.parametrize("path", ["/api/failure", "/failure"])
def test_unknown_failures_have_safe_details_headers_and_diagnostics(error, path, caplog):
    with TestClient(failure_app(error)) as client, caplog.at_level(logging.ERROR):
        response = client.get(path, headers={"X-Request-ID": "request-123"})
        head = client.head(path)
    assert response.status_code == head.status_code == 500
    assert response.headers["x-request-id"] == "request-123"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert head.content == b"" and int(head.headers["content-length"]) > 0
    if path.startswith("/api/"):
        assert response.json()["detail"]["code"] == "internal_error"
    else:
        assert response.headers["content-type"].startswith("text/plain")
    assert "private-secret" not in response.text + caplog.text
    assert "request_id=request-123" in caplog.text and "frames=" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("supplied", [b"", b"a" * 65, b"bad space", b"bad\xff", b"bad\nvalue"])
def test_invalid_request_identifiers_are_replaced(supplied):
    with TestClient(failure_app(RuntimeError("private"))) as client:
        response = client.get("/api/failure", headers=[(b"x-request-id", supplied)])
    identifier = response.headers["x-request-id"]
    assert len(identifier) == 32 and all(value in "0123456789abcdef" for value in identifier)


def test_id_is_preserved_on_success_validation_service_and_security_rejection(api_client):
    cases = [
        ("GET", "/api/auth/me", {}, 200),
        ("GET", "/api/agents/00000000-0000-4000-8000-000000000000", {}, 404),
        ("POST", "/api/auth/login", {"json": {"password": {}}}, 422),
        (
            "POST",
            "/api/auth/login",
            {"json": {}, "headers": {"Origin": "https://untrusted.invalid"}},
            403,
        ),
    ]
    for method, path, options, status in cases:
        headers = {"X-Request-ID": "safe.ID_" + "a" * 56, **options.pop("headers", {})}
        response = api_client.request(method, path, headers=headers, **options)
        assert response.status_code == status
        assert response.headers["x-request-id"] == headers["X-Request-ID"]
    duplicate = api_client.get(
        "/api/auth/me", headers=[("X-Request-ID", "a"), ("X-Request-ID", "b")]
    )
    assert duplicate.headers["x-request-id"] not in {"a", "b", "a, b"}


def http_scope():
    return {"type": "http", "method": "GET", "path": "/api/events", "headers": []}


async def receive():
    return {"type": "http.request", "body": b""}


@pytest.mark.parametrize("complete", [False, True])
def test_started_stream_or_completed_background_fault_never_sends_second_response(complete, caplog):
    messages = []

    async def send(message):
        messages.append(message)

    async def broken(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send(
            {
                "type": "http.response.body",
                "body": b"event: snapshot\n\n",
                "more_body": not complete,
            }
        )
        raise RuntimeError("private-stream-secret")

    with pytest.raises(ResponseStartedFailure) as raised, caplog.at_level(logging.ERROR):
        asyncio.run(FailureBoundaryMiddleware(broken)(http_scope(), receive, send))
    assert len([item for item in messages if item["type"] == "http.response.start"]) == 1
    assert messages[0]["status"] == 200
    assert raised.value.__cause__ is raised.value.__context__ is None
    assert (
        "private-stream-secret"
        not in "".join(traceback.format_exception(raised.value)) + caplog.text
    )


def test_actual_background_task_uses_safe_propagation(caplog):
    app = FastAPI()
    app.add_middleware(FailureBoundaryMiddleware)

    def background():
        raise RuntimeError("private-background-secret")

    @app.get("/api/background")
    def route():
        return Response("already delivered", background=BackgroundTask(background))

    with TestClient(app) as client, pytest.raises(ResponseStartedFailure) as raised:
        client.get("/api/background")
    assert (
        "private-background-secret"
        not in "".join(traceback.format_exception(raised.value)) + caplog.text
    )


def test_cancellation_and_non_http_scopes_are_not_converted():
    async def cancelled(scope, receive, send):
        raise asyncio.CancelledError()

    async def send(message):
        pytest.fail("Cancellation must not start a response")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(FailureBoundaryMiddleware(cancelled)(http_scope(), receive, send))

    scope = {"type": "websocket", "headers": []}

    async def websocket(scope, receive, send):
        assert "state" not in scope
        raise RuntimeError("websocket-original")

    with pytest.raises(RuntimeError, match="websocket-original"):
        asyncio.run(FailureBoundaryMiddleware(websocket)(scope, receive, send))
