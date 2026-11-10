import asyncio
import json
from uuid import uuid4

import pytest
from test_agent_foundations import SearchClient, search_grant
from test_capability_runtime import setup

from app.employees.access import assert_binding
from app.employees.assembly import capture_tools
from app.errors import ConflictError


def member(client):
    service = client.app.state.auth
    actor, token = service.github_login(str(uuid4()), "member", None)
    client.cookies.clear()
    client.cookies.set("app_session", token)
    return actor


def test_employee_uses_fixed_connection_for_every_caller(api_client):
    _, _, agent, _ = setup(api_client)
    connection = search_grant(api_client, agent)
    with api_client.app.state.database.transaction() as db:
        before, _ = capture_tools(db, agent["id"])
    member(api_client)
    assert connection["id"] in {row["id"] for row in api_client.get("/api/tool-connections").json()}
    with api_client.app.state.database.transaction() as db:
        after, _ = capture_tools(db, agent["id"])
        assert_binding(db, {"agent_id": agent["id"]}, after[0])
    assert before == after
    assert after[0]["connection_id"] == connection["id"]
    assert (
        not {"user_id", "account_mode", "personal_binding_id", "raw_descriptor", "metadata"}
        & after[0].keys()
    )
    assert "fixture-tool-secret" not in json.dumps(after)
    assert api_client.get(f"/api/agents/{agent['id']}/my-tool-bindings").status_code == 404
    assert (
        api_client.post(
            "/api/tool-connections",
            json={
                "name": "member",
                "kind": "mcp_http",
                "public_config": {"url": "https://mcp.fixture/mcp"},
            },
        ).status_code
        == 403
    )
    assert (
        api_client.patch(
            f"/api/agents/{agent['id']}", json={"expected_revision": 2, "name": "member edit"}
        ).status_code
        == 403
    )


def test_fixed_connection_revocation_stops_old_binding(api_client):
    _, _, agent, _ = setup(api_client)
    connection = search_grant(api_client, agent)
    with api_client.app.state.database.transaction() as db:
        bindings, _ = capture_tools(db, agent["id"])
    result = api_client.patch(
        f"/api/tool-connections/{connection['id']}",
        json={
            "expected_config_revision": connection["config_revision"],
            "expected_credential_revision": connection["credential_revision"],
            "enabled": False,
        },
    )
    assert result.status_code == 200, result.text
    with api_client.app.state.database.transaction() as db, pytest.raises(ConflictError):
        assert_binding(db, {"agent_id": agent["id"]}, bindings[0])


def test_retired_personal_account_fields_are_rejected(api_client):
    _, _, agent, _ = setup(api_client)
    connection = search_grant(api_client, agent)
    assert (
        api_client.patch(
            f"/api/agents/{agent['id']}",
            json={
                "expected_revision": 2,
                "tool_grants": [
                    {
                        "connection_id": connection["id"],
                        "tools": [],
                        "scope_policy": {},
                        "account_mode": "personal",
                    }
                ],
            },
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            "/api/tool-connections",
            json={
                "name": "legacy",
                "kind": "mcp_http",
                "account_scope": "personal",
                "public_config": {"url": "https://mcp.fixture/mcp"},
            },
        ).status_code
        == 422
    )


def test_catalog_annotations_and_stale_grant_do_not_change_authority(api_client):
    _, _, agent, _ = setup(api_client)
    connection = search_grant(api_client, agent)
    changed = api_client.put(
        f"/api/tool-connections/{connection['id']}/annotations",
        json={
            "expected_annotations_revision": 1,
            "annotations": {"tavily_search": {"display_name": "搜索网页", "note": "展示说明"}},
        },
    )
    assert changed.status_code == 200, changed.text
    assert (
        changed.json()["approved_catalog"][0]["descriptor_hash"]
        == SearchClient.catalog[0]["descriptor_hash"]
    )
    rejected = api_client.patch(
        f"/api/agents/{agent['id']}",
        json={
            "expected_revision": 2,
            "tool_grants": [
                {
                    "connection_id": connection["id"],
                    "tools": ["tavily_search"],
                    "expected_descriptors": {"tavily_search": "old"},
                    "scope_policy": {"mode": "provider"},
                }
            ],
        },
    )
    assert rejected.status_code == 409
    assert api_client.get(f"/api/agents/{agent['id']}").json()["revision"] == 2


def test_config_import_is_inert_and_never_echoes_secrets(api_client):
    value = {
        "mcpServers": {
            "search": {
                "url": "https://mcp.tavily.com/mcp",
                "headers": {"Authorization": "Bearer secret-import-value"},
            }
        }
    }
    preview = api_client.post("/api/mcp-config/preview", json={"configuration": json.dumps(value)})
    assert preview.status_code == 200, preview.text
    assert (
        "secret-import-value" not in preview.text and preview.json()["entries"][0]["has_credential"]
    )
    assert api_client.get("/api/mcp-services").json() == []
    for unsupported in (
        {"command": "node", "args": ["server.js"]},
        {"url": "https://mcp.tavily.com/mcp", "auth": "oauth"},
        {"url": "https://mcp.tavily.com/mcp", "transport": "sse"},
    ):
        assert (
            api_client.post(
                "/api/mcp-config/preview",
                json={"configuration": json.dumps({"mcpServers": {"x": unsupported}})},
            ).status_code
            == 422
        )


def test_protocol_auth_rejection_is_sanitized_and_does_not_start_oauth():
    import httpx

    from app.errors import InvalidInputError
    from app.mcp.adapters.http import MCPClient
    from app.mcp.config import ToolConfig

    calls = []

    def deny(request):
        calls.append(request)
        return httpx.Response(
            401,
            headers={"WWW-Authenticate": 'Bearer resource_metadata="https://other.test/auth"'},
            text="do-not-echo-secret",
        )

    client = MCPClient(
        "https://fixture.test/mcp",
        {"Authorization": "Bearer private-token"},
        ToolConfig(),
        transport_factory=lambda: httpx.MockTransport(deny),
    )
    with pytest.raises(InvalidInputError) as caught:
        asyncio.run(client.discover())
    assert caught.value.code == "tool_auth_required"
    assert (
        "private-token" not in caught.value.message
        and "do-not-echo-secret" not in caught.value.message
    )
    assert calls and all(request.url.host == "fixture.test" for request in calls)


@pytest.mark.parametrize("dns_failure", [False, True])
def test_protocol_preserves_local_network_failures_without_sending_credentials(
    monkeypatch, dns_failure
):
    import socket

    import httpx

    from app.errors import InvalidInputError, ServiceUnavailableError
    from app.mcp.adapters.http import MCPClient
    from app.mcp.config import ToolConfig
    from app.mcp.network import PinnedTransport

    calls = []

    async def scenario():
        async def resolve(*args, **kwargs):
            if dns_failure:
                raise socket.gaierror("private-upstream-diagnostic")
            return [(2, 1, 6, "", ("169.254.169.254", 443))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)

        def transport():
            inner = PinnedTransport("https://mcp.tavily.com/mcp/", ToolConfig())

            def upstream(request):
                calls.append(request)
                return httpx.Response(401)

            inner.inner = httpx.MockTransport(upstream)
            return inner

        client = MCPClient(
            "https://mcp.tavily.com/mcp/",
            {"Authorization": "Bearer private-token"},
            ToolConfig(),
            transport_factory=transport,
        )
        with pytest.raises(ServiceUnavailableError if dns_failure else InvalidInputError) as caught:
            await client.discover()
        assert caught.value.code == ("tool_dns_failed" if dns_failure else "tool_endpoint_denied")
        assert ("DNS" if dns_failure else "链路本地") in caught.value.message
        assert "private-token" not in caught.value.message
        assert "private-upstream-diagnostic" not in caught.value.message

    asyncio.run(scenario())
    assert not calls


@pytest.mark.parametrize(
    "address,allowed",
    [
        ("172.29.0.217", True),
        ("198.18.0.1", True),
        ("127.0.0.1", True),
        ("::1", True),
        ("169.254.169.254", False),
        ("fe80::1", False),
        ("224.0.0.1", False),
        ("ff02::1", False),
        ("0.0.0.0", False),
        ("::", False),
    ],
)
def test_unlisted_host_accepts_private_dns_and_preserves_tls_and_special_address_rejection(
    monkeypatch, address, allowed
):
    import httpx

    from app.errors import InvalidInputError
    from app.mcp.config import ToolConfig
    from app.mcp.network import PinnedTransport

    calls = []

    async def scenario():
        async def resolve(*args, **kwargs):
            return [(2, 1, 6, "", (address, 443))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        endpoint = "https://new-mcp.example/mcp/"
        transport = PinnedTransport(endpoint, ToolConfig())

        def upstream(request):
            calls.append(request)
            assert request.url.host == address
            assert request.headers["host"] == "new-mcp.example"
            assert request.extensions["sni_hostname"] == "new-mcp.example"
            return httpx.Response(401)

        transport.inner = httpx.MockTransport(upstream)
        async with httpx.AsyncClient(transport=transport) as client:
            if allowed:
                assert (await client.post(endpoint)).status_code == 401
            else:
                with pytest.raises(InvalidInputError):
                    await client.post(endpoint)

    asyncio.run(scenario())
    assert len(calls) == int(allowed)


def test_other_admin_can_maintain_shared_employee_and_atomic_save_rolls_back(api_client):
    from app.auth.models import User
    from app.auth.service import hash_password

    _, _, agent, _ = setup(api_client)
    connection = search_grant(api_client, agent)
    failed = api_client.patch(
        f"/api/agents/{agent['id']}",
        json={
            "expected_revision": 2,
            "name": "不应保存的改名",
            "tool_grants": [
                {
                    "connection_id": connection["id"],
                    "tools": ["tavily_search"],
                    "expected_descriptors": {"tavily_search": "stale"},
                    "scope_policy": {"mode": "provider"},
                }
            ],
        },
    )
    assert failed.status_code == 409
    assert api_client.get(f"/api/agents/{agent['id']}").json()["name"] == agent["name"]
    with api_client.app.state.database.transaction() as db:
        db.add(
            User(
                username="another-admin",
                role="admin",
                password_hash=hash_password("another-password"),
            )
        )
    assert (
        api_client.post(
            "/api/auth/login", json={"username": "another-admin", "password": "another-password"}
        ).status_code
        == 200
    )
    assert (
        api_client.patch(
            f"/api/agents/{agent['id']}", json={"expected_revision": 2, "name": "另一管理员维护"}
        ).status_code
        == 200
    )
    assert (
        api_client.patch(
            f"/api/agents/{agent['id']}", json={"expected_revision": 3, "tool_grants": []}
        ).status_code
        == 200
    )


def test_capability_list_is_globally_paginated_without_remote_discovery(api_client):
    api_client.post("/api/skills", json={"name": "同一搜索词 Skill"})
    created = api_client.post(
        "/api/mcp-services", json={"name": "同一搜索词 MCP", "url": "https://mcp.tavily.com/mcp"}
    )
    assert created.status_code == 201
    page = api_client.get("/api/capabilities?q=同一搜索词&limit=1&offset=0").json()
    next_page = api_client.get("/api/capabilities?q=同一搜索词&limit=1&offset=1").json()
    assert page["total"] == next_page["total"] == 2
    assert page["items"][0]["id"] != next_page["items"][0]["id"]
    assert api_client.get("/api/capabilities?kind=mcp_http").json()["total"] == 1


def test_malformed_binding_identifiers_are_rejected_as_input(api_client):
    _, _, agent, _ = setup(api_client)
    invalid = api_client.post(
        "/api/tool-connections",
        json={
            "name": "invalid",
            "kind": "mcp_http",
            "service_id": "not-a-uuid",
            "public_config": {"url": "https://mcp.tavily.com/mcp"},
        },
    )
    assert invalid.status_code == 422
    invalid = api_client.patch(
        f"/api/agents/{agent['id']}",
        json={
            "expected_revision": 1,
            "tool_grants": [{"connection_id": "not-a-uuid", "tools": [], "scope_policy": {}}],
        },
    )
    assert invalid.status_code == 422
