"""Exercise the actual FastAPI SSE route, including request teardown and keepalive."""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import fastapi.routing
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from run_helpers import read_reply, reply_path
from starlette.requests import ClientDisconnect, Request
from starlette.responses import Response
from test_conversations import send, setup_agent

from app.api.dependencies import get_actor, get_conversation_queries
from app.api.errors import register_error_handlers
from app.api.routes.conversations import router
from app.api.streaming import subscribe
from app.auth.permissions import ROLE_PERMISSIONS
from app.errors import AuthenticationError, PermissionDeniedError


def parse_events(text):
    """Read event fields independently of their wire order; ignore comment frames."""
    events = []
    for frame in text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        if "data" in fields:
            fields["data"] = json.loads(fields["data"])
            events.append(fields)
    return events


@pytest.fixture
def observation(api_client):
    _, _, conversation = setup_agent(api_client)
    run = send(api_client, conversation).json()["response"]
    api_client.app.state.run_worker.store.claim(run["id"])
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    initial = api_client.app.state.conversation_queries.response(
        actor, conversation["id"], run["id"]
    )
    snapshots = [initial]
    calls = []

    def read(current_actor, *_ids):
        calls.append(current_actor)
        value = snapshots.pop(0) if len(snapshots) > 1 else snapshots[0]
        if isinstance(value, Exception):
            raise value
        return value

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_conversation_queries] = lambda: SimpleNamespace(response=read)
    app.state.subscriptions = {}
    app.state.runtime_settings = SimpleNamespace(
        subscription_limit=1,
        subscription_seconds=1,
        auth_interval=60,
        poll_interval=0.001,
    )
    app.state.auth = SimpleNamespace(resolve_session=lambda _id: actor)
    return SimpleNamespace(
        app=app,
        path=reply_path(api_client, run["id"]) + "/events",
        actor=actor,
        initial=initial,
        snapshots=snapshots,
        calls=calls,
        run=run,
    )


def final_snapshot(observation):
    initial = observation.initial
    return initial.model_copy(
        update={
            "response": initial.response.model_copy(
                update={
                    "version": initial.response.version + 1,
                    "status": "succeeded",
                    "acceptance": "accepted",
                    "content": '中文\n第二行\r\n"引号"：: event: access.revoked',
                }
            )
        }
    )


def test_native_encoding_versions_terminal_event_and_headers(observation):
    final = final_snapshot(observation)
    observation.snapshots[:] = [
        observation.initial,  # Preflight.
        observation.initial,
        observation.initial,  # Repeated committed version is suppressed.
        final,
    ]
    with TestClient(observation.app) as client:
        response = client.get(observation.path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-accel-buffering"] == "no"
    events = parse_events(response.text)
    assert [item["event"] for item in events] == ["response.snapshot", "response.finished"]
    assert [item["id"] for item in events] == [
        str(observation.initial.response.version),
        str(final.response.version),
    ]
    assert events[-1]["data"] == final.model_dump(mode="json")
    assert len(observation.calls) == 4
    assert observation.app.state.subscriptions == {}


def test_terminal_execution_waits_for_business_acceptance(observation):
    final = final_snapshot(observation)
    pending = final.model_copy(
        update={"response": final.response.model_copy(update={"acceptance": "pending"})}
    )
    accepted = final.model_copy(
        update={
            "response": final.response.model_copy(update={"version": final.response.version + 1})
        }
    )
    observation.snapshots[:] = [pending, pending, accepted]
    with TestClient(observation.app) as client:
        events = parse_events(client.get(observation.path).text)
    assert [item["event"] for item in events] == ["response.snapshot", "response.finished"]
    assert events[0]["data"]["response"]["acceptance"] == "pending"
    assert observation.app.state.subscriptions == {}


def test_official_idle_ping_and_subscription_deadline(observation, monkeypatch):
    # FastAPI imports the keepalive interval into routing; only shorten the test timer.
    monkeypatch.setattr(fastapi.routing, "_PING_INTERVAL", 0.005)
    observation.app.state.runtime_settings.subscription_seconds = 0.05
    observation.app.state.runtime_settings.poll_interval = 0.02
    with TestClient(observation.app) as client:
        response = client.get(observation.path)
    assert ": ping\n\n" in response.text
    assert [item["event"] for item in parse_events(response.text)] == ["response.snapshot"]
    assert observation.app.state.subscriptions == {}


@pytest.mark.parametrize("source", ["session", "permission", "resource"])
def test_revocation_emits_safe_event_and_stops_reading(observation, monkeypatch, source):
    if source == "resource":
        observation.snapshots[:] = [
            observation.initial,
            observation.initial,
            PermissionDeniedError("scope_denied", "private-resource-detail"),
        ]
    else:
        observation.app.state.runtime_settings.auth_interval = 0
        if source == "session":

            def revoked(_id):
                raise AuthenticationError("expired", "private-session-detail")

            observation.app.state.auth.resolve_session = revoked
        else:
            observation.app.state.auth.resolve_session = lambda _id: replace(
                observation.actor, role="guest"
            )
            monkeypatch.setitem(ROLE_PERMISSIONS, "guest", frozenset())
    with TestClient(observation.app) as client:
        response = client.get(observation.path)
    events = parse_events(response.text)
    assert events[-1] == {"event": "access.revoked", "data": {}}
    assert "private-" not in response.text
    assert len(observation.calls) == (3 if source == "resource" else 1)
    assert observation.app.state.subscriptions == {}


def test_preflight_errors_are_http_errors_and_do_not_take_quota(api_client, monkeypatch):
    _, _, conversation = setup_agent(api_client)
    run = send(api_client, conversation).json()["response"]
    path = reply_path(api_client, run["id"]) + "/events"
    token = api_client.cookies.get("app_session")
    actor = api_client.app.state.auth.resolve(token)
    api_client.cookies.clear()
    assert api_client.get(path).status_code == 401
    api_client.cookies.set("app_session", token)
    assert api_client.get(path.replace(run["id"], "999999999999")).status_code == 404
    with monkeypatch.context() as patch:
        patch.setitem(ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] - {"runs:read"})
        assert api_client.get(path).status_code == 403
    counts = api_client.app.state.subscriptions
    assert counts == {}
    counts[actor.user_id] = api_client.app.state.runtime_settings.subscription_limit
    try:
        response = api_client.get(path)
        assert response.status_code == 429 and response.headers["retry-after"] == "2"
        assert response.json()["detail"]["code"] == "subscription_limit"
        assert counts[actor.user_id] == api_client.app.state.runtime_settings.subscription_limit
    finally:
        counts.clear()
    assert counts == {}


def scope(path, version="2.4"):
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": version},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }


@pytest.mark.parametrize("failure", ["headers", "before_iteration", "slow_client", "body"])
def test_send_failure_and_cancellation_release_quota_without_cancelling_run(
    observation, api_client, failure
):
    async def exercise():
        reached = asyncio.Event()
        blocked = asyncio.Event()

        async def receive():
            await blocked.wait()

        async def send_message(message):
            assert observation.app.state.subscriptions == {observation.actor.user_id: 1}
            if message["type"] == "http.response.start":
                if failure == "headers":
                    raise OSError("closed while sending headers")
                if failure == "before_iteration":
                    reached.set()
                    await blocked.wait()
            elif message.get("body"):
                if failure == "body":
                    raise OSError("closed while sending body")
                reached.set()
                await blocked.wait()

        task = asyncio.create_task(observation.app(scope(observation.path), receive, send_message))
        if failure in {"before_iteration", "slow_client"}:
            await asyncio.wait_for(reached.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.RaisesGroup(ClientDisconnect):
                await asyncio.wait_for(task, timeout=2)
        assert observation.app.state.subscriptions == {}

    asyncio.run(exercise())
    assert read_reply(api_client, observation.run["id"])["status"] == "running"


def test_unconsumed_subscription_dependency_still_releases_quota(observation):
    async def exercise():
        request_scope = scope(observation.path)
        request_scope["app"] = observation.app
        dependency = subscribe(
            observation.initial.conversation.id,
            observation.run["id"],
            Request(request_scope),
            Response(),
            observation.actor,
            SimpleNamespace(response=lambda *_args: observation.initial),
        )
        await anext(dependency)
        assert observation.app.state.subscriptions == {observation.actor.user_id: 1}
        await dependency.aclose()
        await dependency.aclose()
        assert observation.app.state.subscriptions == {}

    asyncio.run(exercise())


def test_live_subscription_holds_quota_until_cancelled_then_allows_reconnection(observation):
    async def exercise():
        started = asyncio.Event()
        blocked = asyncio.Event()

        async def receive():
            await blocked.wait()

        async def send_message(message):
            if message["type"] == "http.response.start":
                started.set()
                await blocked.wait()

        task = asyncio.create_task(observation.app(scope(observation.path), receive, send_message))
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=observation.app), base_url="http://testserver"
            ) as client:
                rejected = await client.get(observation.path)
                assert rejected.status_code == 429
                assert observation.app.state.subscriptions == {observation.actor.user_id: 1}
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert observation.app.state.subscriptions == {}
                observation.snapshots[:] = [final_snapshot(observation)]
                resumed = await client.get(observation.path)
                assert resumed.status_code == 200
                assert parse_events(resumed.text)[0]["event"] == "response.finished"
                assert observation.app.state.subscriptions == {}
        finally:
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

    asyncio.run(exercise())


def test_disconnect_signal_releases_quota_without_finishing_run(observation, api_client):
    async def exercise():
        disconnect = asyncio.Event()
        sent = []

        async def receive():
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send_message(message):
            sent.append(message)
            if message.get("body"):
                disconnect.set()

        await asyncio.wait_for(
            observation.app(scope(observation.path, "2.3"), receive, send_message), timeout=2
        )
        assert any(message.get("body") for message in sent)
        assert observation.app.state.subscriptions == {}

    asyncio.run(exercise())
    assert read_reply(api_client, observation.run["id"])["status"] == "running"
