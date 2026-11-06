"""MCP management keeps definitions, credentials and employee references separate."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

from app.employees.tool_grants import assert_connections_unused
from app.errors import ConflictError
from app.mcp.definitions import McpDefinitionService
from app.mcp.models import McpService, ToolConnection
from app.mcp.schemas import McpServiceCreate


def service(client, **changes):
    body = {
        "name": "Context7",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp@4.4.4"],
        **changes,
    }
    client.app.state.tool_connections.config = replace(
        client.app.state.tool_connections.config, stdio_enabled=True
    )
    client.app.state.mcp_definitions.config = client.app.state.tool_connections.config
    result = client.post("/api/mcp-services", json=body)
    assert result.status_code == 201, result.text
    return result.json()


def anonymous(client, definition):
    result = client.post(
        "/api/tool-connections",
        json={
            "name": "我的访问设置",
            "kind": "mcp_stdio",
            "service_id": definition["id"],
            "auth_type": "none",
            "public_config": {
                "command": definition["command"],
                "args": definition["args"],
                "env_keys": [],
            },
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def patch(client, connection, **changes):
    return client.patch(
        f"/api/tool-connections/{connection['id']}",
        json={
            "expected_config_revision": connection["config_revision"],
            "expected_credential_revision": connection["credential_revision"],
            **changes,
        },
    )


def test_existing_anonymous_connection_can_add_key_without_recreating_service(api_client):
    definition = service(api_client)
    connection = anonymous(api_client, definition)
    edited = api_client.patch(
        f"/api/mcp-services/{definition['id']}",
        json={"expected_revision": 1, "env_keys": ["CONTEXT7_API_KEY"]},
    )
    assert edited.status_code == 200, edited.text
    # Adding an allowed field does not silently change an anonymous identity.
    assert api_client.get("/api/tool-connections").json()[0]["auth_type"] == "none"
    with api_client.app.state.database.transaction() as db:
        row = db.get(ToolConnection, connection["id"])
        row.approved_catalog = [{"name": "query-docs", "descriptor_hash": "old"}]
    changed = patch(
        api_client,
        connection,
        auth_type="env",
        environment={"CONTEXT7_API_KEY": "new-personal-secret"},
    )
    assert changed.status_code == 200, changed.text
    configured = changed.json()
    assert configured["id"] == connection["id"] and configured["has_credential"]
    assert configured["approved_catalog"] == []
    assert configured["credential_revision"] > connection["credential_revision"]
    assert "new-personal-secret" not in changed.text
    assert "new-personal-secret" not in api_client.get("/api/tool-connections").text
    denied = patch(api_client, configured, environment={"NODE_OPTIONS": "--eval=bad"})
    assert denied.status_code == 422
    remove_field = api_client.patch(
        f"/api/mcp-services/{definition['id']}", json={"expected_revision": 2, "env_keys": []}
    )
    assert remove_field.status_code == 409
    cleared = patch(api_client, configured, auth_type="none")
    assert cleared.status_code == 200, cleared.text
    assert not cleared.json()["has_credential"]
    assert cleared.json()["public_config"]["env_keys"] == []
    assert patch(api_client, connection, enabled=False).status_code == 409


def test_http_auth_can_change_from_anonymous_to_key_and_back(api_client):
    created = api_client.post(
        "/api/tool-connections",
        json={
            "name": "HTTP",
            "kind": "mcp_http",
            "auth_type": "none",
            "public_config": {"url": "https://mcp.tavily.com/mcp"},
        },
    )
    assert created.status_code == 201, created.text
    changed = patch(api_client, created.json(), auth_type="bearer", credential="personal-secret")
    assert changed.status_code == 200 and changed.json()["has_credential"]
    renamed = patch(api_client, changed.json(), name="我的 Key")
    assert renamed.status_code == 200 and renamed.json()["has_credential"]
    cleared = patch(api_client, renamed.json(), auth_type="none")
    assert cleared.status_code == 200 and not cleared.json()["has_credential"]


def test_duplicate_service_definition_and_casefolded_name_are_rejected(api_client):
    original = service(api_client)
    duplicate = api_client.post(
        "/api/mcp-services",
        json={
            "name": "另一个名字",
            "transport": "stdio",
            "command": "bunx",
            "args": ["--yes", "@upstash/context7-mcp@4.4.4"],
            "env_keys": ["API_KEY"],
        },
    )
    assert duplicate.status_code == 409
    same_name = api_client.post(
        "/api/mcp-services",
        json={"name": " context7 ", "transport": "http", "url": "https://mcp.tavily.com/mcp"},
    )
    assert same_name.status_code == 409
    assert len(api_client.get("/api/mcp-services").json()) == 1
    assert original["name"] == "Context7"


def test_concurrent_service_creation_has_one_winner(api_client):
    database = api_client.app.state.database
    config = api_client.app.state.tool_connections.config
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    barrier = Barrier(2)

    def create(index):
        barrier.wait(timeout=5)
        try:
            McpDefinitionService(
                database, config, check_references=assert_connections_unused
            ).create(
                actor, McpServiceCreate(name=f"HTTP {index}", url="https://mcp.tavily.com/mcp")
            )
            return "created"
        except ConflictError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, (1, 2)))
    assert sorted(results) == ["created", "mcp_service_exists"]


def test_service_deletion_removes_only_unused_owned_connections(api_client):
    definition = service(api_client)
    connection = anonymous(api_client, definition)
    stale = api_client.delete(f"/api/mcp-services/{definition['id']}?expected_revision=2")
    assert stale.status_code == 409
    deleted = api_client.delete(f"/api/mcp-services/{definition['id']}?expected_revision=1")
    assert deleted.status_code == 204, deleted.text
    assert api_client.get("/api/mcp-services").json() == []
    assert api_client.get("/api/tool-connections").json() == []
    assert patch(api_client, connection, enabled=False).status_code == 404


def test_employee_reference_blocks_service_and_connection_deletion(api_client):
    from test_agent_foundations import search_grant
    from test_capability_runtime import setup

    _, _, agent, _ = setup(api_client)
    connection = search_grant(api_client, agent)
    rows = api_client.get("/api/mcp-services").json()
    definition = next(row for row in rows if row["id"] == connection["service_id"])
    assert (
        api_client.delete(
            f"/api/mcp-services/{definition['id']}?expected_revision={definition['revision']}"
        ).status_code
        == 409
    )
    assert (
        api_client.delete(
            f"/api/tool-connections/{connection['id']}?expected_config_revision={connection['config_revision']}&expected_credential_revision={connection['credential_revision']}"
        ).status_code
        == 409
    )
    with api_client.app.state.database.transaction() as db:
        assert db.get(McpService, definition["id"]) is not None
        assert db.get(ToolConnection, connection["id"]) is not None


def test_other_users_connections_block_service_deletion(api_client):
    from test_mcp_accounts import member

    definition = service(api_client)
    cookies = dict(api_client.cookies)
    member(api_client)
    connection = anonymous(api_client, definition)
    api_client.cookies.clear()
    api_client.cookies.update(cookies)
    assert (
        api_client.delete(f"/api/mcp-services/{definition['id']}?expected_revision=1").status_code
        == 409
    )
    assert (
        api_client.delete(
            f"/api/tool-connections/{connection['id']}?expected_config_revision=1&expected_credential_revision=1"
        ).status_code
        == 404
    )


def test_unchanged_catalog_does_not_require_reapproval(api_client):
    from test_agent_foundations import search_grant
    from test_capability_runtime import setup

    _, _, agent, _ = setup(api_client)
    connection = search_grant(api_client, agent)
    before = next(
        item
        for item in api_client.get("/api/tool-connections").json()
        if item["id"] == connection["id"]
    )
    refreshed = api_client.post(f"/api/tool-connections/{connection['id']}/discover")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["discovery_candidate"] is None
    assert refreshed.json()["catalog_revision"] == before["catalog_revision"]
