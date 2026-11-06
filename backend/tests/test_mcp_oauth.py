"""Exercise browser callbacks and durable tokens through the official MCP SDK."""

import asyncio
import base64
import hashlib
import json
import logging
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.api.oauth_logging import OAuthAccessFilter
from app.errors import InvalidInputError
from app.mcp.adapters.http import MCPClient
from app.mcp.models import ToolConnection
from app.mcp.oauth import OAuthService


class OAuthServer:
    def __init__(self):
        self.registration_count = self.refresh_count = self.business_calls = 0
        self.refresh_failure = None
        self.refuse_access = False
        self.authorization = {}
        self.requests = []
        self.catalog = [
            {
                "name": "lookup",
                "description": "Look up a test value",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]

    def request(self, request):
        self.requests.append((str(request.url), request.method))
        path = request.url.path
        if path == "/.well-known/oauth-protected-resource":
            assert "authorization" not in request.headers
            return httpx.Response(
                200,
                json={
                    "resource": "https://mcp.fixture/mcp",
                    "authorization_servers": ["https://auth.fixture"],
                },
            )
        if path == "/.well-known/oauth-authorization-server":
            return httpx.Response(
                200,
                json={
                    "issuer": "https://auth.fixture",
                    "authorization_endpoint": "https://auth.fixture/authorize",
                    "token_endpoint": "https://auth.fixture/token",
                    "registration_endpoint": "https://auth.fixture/register",
                    "response_types_supported": ["code"],
                    "code_challenge_methods_supported": ["S256"],
                },
            )
        if path == "/register":
            self.registration_count += 1
            return httpx.Response(
                201,
                json={
                    "client_id": "fixture-client",
                    "redirect_uris": ["http://localhost:3000/api/tool-connections/oauth/callback"],
                    "token_endpoint_auth_method": "none",
                },
            )
        if path == "/token":
            data = parse_qs(request.content.decode())
            if data["grant_type"] == ["authorization_code"]:
                challenge = (
                    base64.urlsafe_b64encode(
                        hashlib.sha256(data["code_verifier"][0].encode()).digest()
                    )
                    .decode()
                    .rstrip("=")
                )
                assert challenge == self.authorization["code_challenge"][0]
            else:
                assert request.url.host == "auth.fixture"
                self.refresh_count += 1
                if self.refresh_failure:
                    return httpx.Response(
                        self.refresh_failure[0], json={"error": self.refresh_failure[1]}
                    )
            return httpx.Response(
                200,
                json={
                    "access_token": "fixture-access",
                    "token_type": "Bearer",
                    "refresh_token": f"fixture-refresh-{self.refresh_count}",
                    "expires_in": 3600,
                },
            )
        if path == "/mcp":
            if (
                self.refuse_access
                or request.headers.get("authorization") != "Bearer fixture-access"
            ):
                return httpx.Response(
                    401,
                    headers={
                        "WWW-Authenticate": 'Bearer resource_metadata="https://mcp.fixture/.well-known/oauth-protected-resource"'
                    },
                )
            if request.method != "POST":
                return httpx.Response(405)
            body = json.loads(request.content)
            method = body["method"]
            if "id" not in body:
                return httpx.Response(202)
            if method == "initialize":
                result = {
                    "protocolVersion": body["params"]["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture", "version": "1"},
                }
            elif method == "tools/list":
                result = {"tools": self.catalog}
            elif method == "tools/call":
                self.business_calls += 1
                result = {"content": [{"type": "text", "text": "fixture result"}]}
            else:
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "error": {"code": -32601, "message": "Method not found"},
                    },
                )
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})
        raise AssertionError(str(request.url))


def setup_oauth(client):
    server = OAuthServer()

    def factory():
        return httpx.MockTransport(server.request)

    client.app.state.tool_oauth.transport_factory = factory
    client.app.state.tool_invocation.client_factory = lambda endpoint, headers, config, **kwargs: (
        MCPClient(endpoint, headers, config, transport_factory=factory, **kwargs)
    )
    response = client.post(
        "/api/tool-connections",
        json={
            "name": "OAuth fixture",
            "kind": "mcp_http",
            "auth_type": "oauth",
            "public_config": {"url": "https://mcp.fixture/mcp"},
        },
    )
    assert response.status_code == 201, response.text
    assert not response.json()["has_credential"]
    return server, response.json()


def poll(client, connection, session, expected):
    for _ in range(150):
        response = client.get(
            f"/api/tool-connections/{connection['id']}/oauth/sessions/{session['id']}"
        )
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] in expected:
            return result
        time.sleep(0.01)
    pytest.fail(str(result))


def begin_authorization(client, connection):
    started = client.post(
        f"/api/tool-connections/{connection['id']}/oauth/sessions",
        json={
            "expected_config_revision": connection["config_revision"],
            "expected_credential_revision": connection["credential_revision"],
        },
    )
    assert started.status_code == 202, started.text
    session = poll(client, connection, started.json(), {"awaiting_consent", "failed"})
    assert session["status"] == "awaiting_consent", session
    return session


def authorize(client, server, connection):
    session = begin_authorization(client, connection)
    server.authorization = parse_qs(urlsplit(session["authorization_url"]).query)
    response = client.get(
        "/api/tool-connections/oauth/callback",
        params={
            "state": server.authorization["state"][0],
            "code": "fixture-code",
            "iss": "https://auth.fixture",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    assert "code=" not in response.headers["location"]
    result = poll(client, connection, session, {"succeeded", "failed"})
    assert result["status"] == "succeeded", result
    saved = client.get("/api/tool-connections").json()
    return next(row for row in saved if row["id"] == connection["id"]), session


def expire(client, connection):
    service = client.app.state.tool_connections
    with client.app.state.database.transaction() as db:
        row = db.get(ToolConnection, connection["id"])
        payload = json.loads(service._decrypt(row))
        payload["expires_at"] = time.time() - 10
        row.encrypted_credentials = service.encrypt_oauth(payload)


def test_standard_authorization_catalog_and_refresh_preserve_grant(api_client):
    server, connection = setup_oauth(api_client)
    saved, session = authorize(api_client, server, connection)
    assert saved["oauth_status"] == "connected" and saved["has_credential"]
    assert server.registration_count == 1
    candidate = api_client.post(f"/api/tool-connections/{saved['id']}/discover")
    assert candidate.status_code == 200, candidate.text
    assert candidate.json()["discovery_candidate"]["tools"][0]["name"] == "lookup"
    assert "fixture-access" not in candidate.text and "fixture-refresh" not in candidate.text
    expire(api_client, saved)
    result = api_client.post(f"/api/tool-connections/{saved['id']}/discover")
    assert result.status_code == 200, result.text
    assert server.refresh_count == 1 and server.registration_count == 1
    assert result.json()["credential_revision"] == saved["credential_revision"]
    replay = api_client.get(
        "/api/tool-connections/oauth/callback",
        params={"state": server.authorization["state"][0], "code": "fixture-code"},
        follow_redirects=False,
    )
    assert "oauth_error" in replay.headers["location"]


@pytest.mark.parametrize(
    "status,error,expected", [(400, "invalid_grant", 422), (503, "temporarily_unavailable", 503)]
)
def test_refresh_failure_is_classified_without_reauthorization(api_client, status, error, expected):
    server, connection = setup_oauth(api_client)
    saved, _ = authorize(api_client, server, connection)
    expire(api_client, saved)
    server.refresh_failure = status, error
    response = api_client.post(f"/api/tool-connections/{saved['id']}/discover")
    assert response.status_code == expected, response.text
    assert server.registration_count == 1
    current = api_client.get("/api/tool-connections").json()[0]
    assert current["oauth_status"] == ("reauth_required" if expected == 422 else "connected")


def test_cancel_and_origin_cannot_consume_authorization(api_client):
    server, connection = setup_oauth(api_client)
    data = {"expected_config_revision": 1, "expected_credential_revision": 1}
    denied = api_client.post(
        f"/api/tool-connections/{connection['id']}/oauth/sessions",
        json=data,
        headers={"Origin": "http://127.0.0.1:3000"},
    )
    assert denied.status_code == 422
    started = api_client.post(
        f"/api/tool-connections/{connection['id']}/oauth/sessions", json=data
    ).json()
    session = poll(api_client, connection, started, {"awaiting_consent", "failed"})
    assert session["status"] == "awaiting_consent", session
    assert (
        api_client.delete(
            f"/api/tool-connections/{connection['id']}/oauth/sessions/{session['id']}"
        ).status_code
        == 204
    )
    assert poll(api_client, connection, session, {"cancelled"})["status"] == "cancelled"
    assert server.business_calls == 0


def test_restart_concurrent_refresh_and_business_guard(api_client):
    server, connection = setup_oauth(api_client)
    saved, _ = authorize(api_client, server, connection)
    expire(api_client, saved)
    previous = api_client.app.state.tool_oauth
    restarted = OAuthService(
        previous.connections, previous.auth, transport_factory=previous.transport_factory
    )
    with api_client.app.state.database.transaction() as db:
        row = db.get(ToolConnection, saved["id"])
    factory = api_client.app.state.tool_invocation.client_factory

    async def scenario():
        async def read():
            return await factory(
                row.public_config["url"], {}, restarted.config, access=lambda: restarted.access(row)
            ).discover()

        catalogs = await asyncio.gather(read(), read())
        assert catalogs[0] == catalogs[1]
        client = factory(
            row.public_config["url"], {}, restarted.config, access=lambda: restarted.access(row)
        )

        async def reject():
            raise InvalidInputError("test_revoked", "revoked")

        with pytest.raises(InvalidInputError, match="revoked"):
            await client.invoke("lookup", {}, catalogs[0][0]["descriptor_hash"], reject)
        assert server.business_calls == 0

        async def permit():
            pass

        value, _, status = await client.invoke(
            "lookup", {}, catalogs[0][0]["descriptor_hash"], permit
        )
        assert status == "success" and "fixture result" in str(value)
        await restarted.close()

    api_client.portal.call(scenario)
    assert server.refresh_count == 1 and server.registration_count == 1
    assert server.business_calls == 1


def test_wrong_state_changed_login_and_cancelled_callback(api_client):
    _, connection = setup_oauth(api_client)
    session = begin_authorization(api_client, connection)
    state = parse_qs(urlsplit(session["authorization_url"]).query)["state"][0]
    for supplied in ["wrong-state", ""]:
        result = api_client.get(
            "/api/tool-connections/oauth/callback",
            params={"state": supplied, "code": "code"},
            follow_redirects=False,
        )
        assert "oauth_error" in result.headers["location"]
    api_client.post("/api/auth/logout")
    assert (
        api_client.post(
            "/api/auth/login", json={"username": "admin", "password": "test-password-auth"}
        ).status_code
        == 200
    )
    result = api_client.get(
        "/api/tool-connections/oauth/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert "oauth_error" in result.headers["location"]
    assert not api_client.get("/api/tool-connections").json()[0]["has_credential"]


def test_disconnect_invalidates_grant_and_reuses_registration(api_client):
    server, connection = setup_oauth(api_client)
    saved, _ = authorize(api_client, server, connection)
    response = api_client.post(
        f"/api/tool-connections/{saved['id']}/oauth/disconnect",
        json={
            "expected_config_revision": saved["config_revision"],
            "expected_credential_revision": saved["credential_revision"],
        },
    )
    assert response.status_code == 200, response.text
    disconnected = response.json()
    assert disconnected["oauth_status"] == "disconnected" and not disconnected["has_credential"]
    assert disconnected["credential_revision"] > saved["credential_revision"]
    assert api_client.post(f"/api/tool-connections/{saved['id']}/discover").status_code == 422
    reconnected, _ = authorize(api_client, server, disconnected)
    assert reconnected["oauth_status"] == "connected"
    assert server.registration_count == 1


def test_changed_configuration_rejects_late_token_write(api_client):
    _, connection = setup_oauth(api_client)
    session = begin_authorization(api_client, connection)
    state = parse_qs(urlsplit(session["authorization_url"]).query)["state"][0]
    row = api_client.get("/api/tool-connections").json()[0]
    response = api_client.patch(
        f"/api/tool-connections/{row['id']}",
        json={
            "expected_config_revision": row["config_revision"],
            "expected_credential_revision": row["credential_revision"],
            "enabled": False,
        },
    )
    assert response.status_code == 200, response.text
    result = api_client.get(
        "/api/tool-connections/oauth/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert "oauth_error" in result.headers["location"]
    assert not api_client.get("/api/tool-connections").json()[0]["has_credential"]


@pytest.mark.parametrize(
    "callback", ["/api/tool-connections/oauth/callback", "/api/auth/github/callback"]
)
def test_callback_access_log_drops_all_secrets(callback):
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        (
            "client",
            "GET",
            f"{callback}?code=secret&state=hidden",
            "1.1",
            303,
        ),
        None,
    )
    OAuthAccessFilter().filter(record)
    assert "secret" not in record.getMessage() and "hidden" not in record.getMessage()


def test_preregistered_client_skips_dynamic_registration(api_client):
    server, connection = setup_oauth(api_client)
    patched = api_client.patch(
        f"/api/tool-connections/{connection['id']}",
        json={
            "expected_config_revision": 1,
            "expected_credential_revision": 1,
            "public_config": {
                "url": "https://mcp.fixture/mcp",
                "oauth": {"client_id": "pre-registered"},
            },
            "oauth_client_secret": "fixture-client-secret",
        },
    )
    assert patched.status_code == 200, patched.text
    assert "fixture-client-secret" not in patched.text
    saved, _ = authorize(api_client, server, patched.json())
    assert saved["oauth_status"] == "connected"
    assert server.registration_count == 0


def test_refresh_storage_failure_blocks_further_network_requests(api_client, monkeypatch):
    server, connection = setup_oauth(api_client)
    saved, _ = authorize(api_client, server, connection)
    expire(api_client, saved)
    from app.mcp.oauth_storage import OAuthStorage

    async def fail(*args, **kwargs):
        raise RuntimeError("disk unavailable")

    monkeypatch.setattr(OAuthStorage, "set_tokens", fail)
    failed = api_client.post(f"/api/tool-connections/{saved['id']}/discover")
    assert failed.status_code == 503
    count = len(server.requests)
    again = api_client.post(f"/api/tool-connections/{saved['id']}/discover")
    assert again.status_code == 422
    assert len(server.requests) == count and server.refresh_count == 1


def test_downgrade_refuses_to_discard_oauth_accounts(historical_api_client):
    api_client = historical_api_client
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    setup_oauth(api_client)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.raises(RuntimeError, match="仍有 OAuth 账号"):
        command.downgrade(config, "0017")


def test_another_user_cannot_poll_or_consume_authorization(api_client):
    from uuid import uuid4

    _, connection = setup_oauth(api_client)
    session = begin_authorization(api_client, connection)
    state = parse_qs(urlsplit(session["authorization_url"]).query)["state"][0]
    _, token = api_client.app.state.auth.github_login(str(uuid4()), "oauth-other", None)
    api_client.cookies.clear()
    api_client.cookies.set("app_session", token)
    assert (
        api_client.get(
            f"/api/tool-connections/{connection['id']}/oauth/sessions/{session['id']}"
        ).status_code
        == 404
    )
    response = api_client.get(
        "/api/tool-connections/oauth/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert "oauth_error" in response.headers["location"]


def test_upstream_401_requires_reconnect_without_new_authorization(api_client):
    server, connection = setup_oauth(api_client)
    saved, _ = authorize(api_client, server, connection)
    server.refuse_access = True
    result = api_client.post(f"/api/tool-connections/{saved['id']}/discover")
    assert result.status_code == 422, result.text
    row = api_client.get("/api/tool-connections").json()[0]
    assert row["oauth_status"] == "reauth_required" and not row["has_credential"]
    assert server.registration_count == 1 and server.refresh_count == 0


def test_duplicate_start_and_configuration_change_before_callback(api_client):
    server, connection = setup_oauth(api_client)
    session = begin_authorization(api_client, connection)
    duplicate = api_client.post(
        f"/api/tool-connections/{connection['id']}/oauth/sessions",
        json={
            "expected_config_revision": connection["config_revision"],
            "expected_credential_revision": connection["credential_revision"],
        },
    )
    assert duplicate.status_code == 202 and duplicate.json()["id"] == session["id"]
    row = api_client.get("/api/tool-connections").json()[0]
    assert (
        api_client.patch(
            f"/api/tool-connections/{row['id']}",
            json={
                "expected_config_revision": row["config_revision"],
                "expected_credential_revision": row["credential_revision"],
                "name": "Changed while authorizing",
            },
        ).status_code
        == 200
    )
    state = parse_qs(urlsplit(session["authorization_url"]).query)["state"][0]
    count = len(server.requests)
    result = api_client.get(
        "/api/tool-connections/oauth/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert "oauth_error" in result.headers["location"]
    assert len(server.requests) == count


def test_capacity_and_expired_callback(api_client):
    from dataclasses import replace

    server, connection = setup_oauth(api_client)
    service = api_client.app.state.tool_oauth
    service.config = replace(service.config, oauth_max_sessions=1)
    session = begin_authorization(api_client, connection)
    other = api_client.post(
        "/api/tool-connections",
        json={
            "name": "Another OAuth",
            "kind": "mcp_http",
            "auth_type": "oauth",
            "public_config": {"url": "https://mcp.fixture/mcp"},
        },
    ).json()
    result = api_client.post(
        f"/api/tool-connections/{other['id']}/oauth/sessions",
        json={"expected_config_revision": 1, "expected_credential_revision": 1},
    )
    assert result.status_code == 503
    service.sessions[session["id"]].deadline = time.time() - 1
    state = parse_qs(urlsplit(session["authorization_url"]).query)["state"][0]
    result = api_client.get(
        "/api/tool-connections/oauth/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert "oauth_error" in result.headers["location"]
    assert poll(api_client, connection, session, {"expired"})["status"] == "expired"
    assert server.business_calls == 0


def test_cancelling_after_token_commit_disconnects_the_new_grant(api_client, monkeypatch):
    from app.mcp.oauth_storage import OAuthStorage

    original = OAuthStorage.set_tokens

    async def pause_after_commit(storage, tokens):
        await original(storage, tokens)
        await asyncio.Event().wait()

    monkeypatch.setattr(OAuthStorage, "set_tokens", pause_after_commit)
    server, connection = setup_oauth(api_client)
    session = begin_authorization(api_client, connection)
    server.authorization = parse_qs(urlsplit(session["authorization_url"]).query)
    state = server.authorization["state"][0]
    assert (
        api_client.get(
            "/api/tool-connections/oauth/callback",
            params={"state": state, "code": "code"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    for _ in range(150):
        if api_client.get("/api/tool-connections").json()[0]["has_credential"]:
            break
        time.sleep(0.01)
    else:
        pytest.fail("token commit did not complete")
    assert (
        api_client.delete(
            f"/api/tool-connections/{connection['id']}/oauth/sessions/{session['id']}"
        ).status_code
        == 204
    )
    assert poll(api_client, connection, session, {"cancelled"})["status"] == "cancelled"
    assert not api_client.get("/api/tool-connections").json()[0]["has_credential"]


def test_disabled_connection_can_disconnect_but_not_authorize(api_client):
    server, connection = setup_oauth(api_client)
    saved, _ = authorize(api_client, server, connection)
    disabled = api_client.patch(
        f"/api/tool-connections/{saved['id']}",
        json={
            "expected_config_revision": saved["config_revision"],
            "expected_credential_revision": saved["credential_revision"],
            "enabled": False,
        },
    ).json()
    data = {
        "expected_config_revision": disabled["config_revision"],
        "expected_credential_revision": disabled["credential_revision"],
    }
    assert (
        api_client.post(
            f"/api/tool-connections/{saved['id']}/oauth/sessions", json=data
        ).status_code
        == 422
    )
    result = api_client.post(f"/api/tool-connections/{saved['id']}/oauth/disconnect", json=data)
    assert result.status_code == 200, result.text
    assert not result.json()["has_credential"]


@pytest.mark.parametrize(
    "count,description,duplicate,expected,message",
    [
        (68, "x" * 4500, False, 200, None),
        (68, "文" * 1500, False, 200, None),
        (129, "description", False, 422, "128"),
        (1, "x" * 600_000, False, 422, "1024 KiB"),
        (2, "description", True, 422, "重复"),
    ],
)
def test_catalog_size_count_and_duplicate_boundaries(
    api_client, count, description, duplicate, expected, message
):
    server, connection = setup_oauth(api_client)
    saved, _ = authorize(api_client, server, connection)
    server.catalog = [
        {
            "name": "lookup" if duplicate else f"lookup_{index}",
            "description": description,
            "inputSchema": {"type": "object", "properties": {}},
        }
        for index in range(count)
    ]
    result = api_client.post(f"/api/tool-connections/{saved['id']}/discover")
    assert result.status_code == expected, result.text[:500]
    if expected == 200:
        candidate = result.json()["discovery_candidate"]
        assert len(candidate["tools"]) == 68
        assert len(json.dumps(candidate["tools"]).encode()) > 256 * 1024
        assert not result.json()["approved_catalog"]
    else:
        assert message in result.json()["detail"]["message"]
