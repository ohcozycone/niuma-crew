"""Business operations remain safe without HTTP, and routes keep transport responsibilities."""

import ast
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.sse import EventSourceResponse
from sqlalchemy import event, select
from starlette.responses import Response, StreamingResponse
from test_configuration_api import create_agent, create_skill

from app.api.router import router
from app.capability_catalog.queries import list_capabilities
from app.capability_catalog.schemas import CapabilityRead
from app.employees.models import Agent
from app.employees.schemas import AgentCreate, AgentPatch
from app.employees.service import AgentService
from app.errors import InvalidInputError, PermissionDeniedError
from app.skills.service import SkillService


def current_actor(client):
    return client.app.state.auth.resolve(client.cookies.get("app_session"))


@pytest.mark.parametrize("operation", ["update", "delete", "grants"])
def test_direct_employee_write_rejects_non_creator_and_preserves_data(api_client, operation):
    agent = create_agent(api_client, system_prompt="原始岗位指令")
    actor = replace(current_actor(api_client), user_id=str(uuid4()))
    commands = api_client.app.state.agents
    with pytest.raises(PermissionDeniedError, match="创建者"):
        if operation == "update":
            commands.update(agent["id"], AgentPatch(expected_revision=1, name="不得保存"), actor)
        elif operation == "delete":
            commands.delete(agent["id"], actor)
        else:
            api_client.app.state.agents.update(
                agent["id"], AgentPatch(expected_revision=1, tool_grants=[]), actor
            )
    assert api_client.get(f"/api/agents/{agent['id']}").json() == agent


def test_direct_employee_creation_requires_operation_permission(api_client):
    actor = replace(current_actor(api_client), role="member")
    with pytest.raises(PermissionDeniedError):
        api_client.app.state.agents.create(AgentCreate(name="不能创建", avatar_id="admin"), actor)
    assert api_client.get("/api/agents").json()["total"] == 0


@pytest.mark.parametrize("operation", ["update", "delete", "grants"])
def test_employee_edit_checks_and_writes_share_one_transaction(api_client, monkeypatch, operation):
    agent = create_agent(api_client)
    actor = current_actor(api_client)
    database = api_client.app.state.database
    original = database.transaction
    transactions = []

    @contextmanager
    def tracked():
        with original() as session:
            transactions.append(session)
            yield session

    monkeypatch.setattr(database, "transaction", tracked)
    if operation == "update":
        api_client.app.state.agents.update(
            agent["id"], AgentPatch(expected_revision=1, name="新名称"), actor
        )
    elif operation == "delete":
        api_client.app.state.agents.delete(agent["id"], actor)
    else:
        api_client.app.state.agents.update(
            agent["id"], AgentPatch(expected_revision=1, tool_grants=[]), actor
        )
    assert len(transactions) == 1


def test_employee_write_failure_rolls_back_fields_and_revision(api_client, monkeypatch):
    agent = create_agent(api_client)

    def fail(*args):
        raise InvalidInputError("injected_grant_failure", "装配拒绝。")

    monkeypatch.setattr("app.employees.service.apply_grants", fail)
    with pytest.raises(InvalidInputError):
        api_client.app.state.agents.update(
            agent["id"],
            AgentPatch(expected_revision=1, name="不得部分保存", tool_grants=[]),
            current_actor(api_client),
        )
    assert api_client.get(f"/api/agents/{agent['id']}").json() == agent


def test_legacy_employee_remains_editable_by_admin(api_client):
    agent = create_agent(api_client)
    with api_client.app.state.database.transaction() as db:
        db.get(Agent, agent["id"]).created_by_user_id = None
    updated = api_client.app.state.agents.update(
        agent["id"], AgentPatch(expected_revision=1, name="历史员工"), current_actor(api_client)
    )
    assert updated.name == "历史员工" and updated.revision == 2


def test_public_detail_queries_never_load_private_bodies_or_assembly_parameters(api_client):
    skill = create_skill(api_client, instructions="PRIVATE_METHOD")
    agent = create_agent(
        api_client,
        system_prompt="PRIVATE_PROMPT",
        skill_assignments=[{"skill_id": skill["id"], "parameters": {}}],
    )
    statements = []
    engine = api_client.app.state.database.engine

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
        employee = api_client.app.state.agents.get_public(agent["id"], actor)
        method = api_client.app.state.skills.get_public(skill["id"], actor)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert str(employee.skill_ids[0]) == skill["id"] and method.assignment_count == 1
    for statement in statements:
        assert not any(
            field in statement
            for field in (
                "agents.system_prompt",
                "skills.instructions",
                "skills.skill_md",
                "skills.configuration_schema",
                "agent_skills.parameters",
            )
        ), statement


def test_display_and_usage_reuse_configured_services_without_management_reads(
    api_client, monkeypatch
):
    skill = create_skill(api_client)
    agent = create_agent(api_client, skill_assignments=[{"skill_id": skill["id"]}])

    def forbidden(*args, **kwargs):
        raise AssertionError("Display reads must use configured services and direct projections")

    monkeypatch.setattr(SkillService, "__init__", forbidden)
    monkeypatch.setattr(AgentService, "__init__", forbidden)
    monkeypatch.setattr(api_client.app.state.agents, "get", forbidden)
    monkeypatch.setattr(api_client.app.state.skills, "get", forbidden)
    for path in (
        "/api/public/agents",
        "/api/public/skills",
        f"/api/public/agents/{agent['id']}",
        f"/api/public/skills/{skill['id']}",
        f"/api/agents/{agent['id']}/usage",
    ):
        assert api_client.get(path).status_code == 200


def test_catalog_visibility_applies_before_global_count_and_pagination(api_client):
    create_skill(api_client, name="目录 Skill")
    api_client.post(
        "/api/mcp-services", json={"name": "目录 MCP", "url": "https://mcp.tavily.com/mcp"}
    )
    database = api_client.app.state.database
    admin = current_actor(api_client)
    first = list_capabilities(database, admin, q="目录", limit=1)
    second = list_capabilities(database, admin, q="目录", limit=1, offset=1)
    assert first.total == second.total == 2
    assert first.items[0].id != second.items[0].id
    guest, _ = api_client.app.state.auth.guest(None)
    visible = list_capabilities(database, guest, q="目录", limit=1)
    assert visible.total == 1 and visible.items[0].kind == "skill"
    assert list_capabilities(database, guest, kind="mcp_http").total == 0
    with pytest.raises(InvalidInputError) as failure:
        list_capabilities(database, admin, kind="unexpected")
    assert failure.value.code == "capability_query_invalid"


def test_catalog_timestamp_keeps_existing_wire_format():
    value = CapabilityRead(
        id=str(uuid4()),
        name="目录",
        description="",
        kind="skill",
        enabled=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        protocol_name="catalog",
    )
    assert value.model_dump(mode="json")["created_at"] == "2026-01-01T00:00:00+00:00"


def test_connection_reference_guard_runs_in_the_deleting_transaction(api_client):
    result = api_client.post(
        "/api/tool-connections",
        json={"name": "原生工作区", "kind": "native", "provider_key": "workspace"},
    )
    assert result.status_code == 201, result.text
    connection = result.json()
    tools = api_client.app.state.workspace_profiles
    original = tools.check_references
    calls = []

    def checked(session, ids):
        assert session.in_transaction()
        assert session.scalar(select(Agent.id)) is None
        calls.append(ids)
        original(session, ids)

    tools.check_references = checked
    result = api_client.delete(
        f"/api/tool-connections/{connection['id']}",
        params={"expected_config_revision": 1, "expected_credential_revision": 1},
    )
    assert result.status_code == 204 and calls == [[connection["id"]]]


def test_json_endpoints_declare_response_models_and_protocols_keep_own_responses():
    for route in router.routes:
        if (
            not isinstance(route, APIRoute)
            or not route.include_in_schema
            or route.status_code == 204
        ):
            continue
        if route.response_class in (Response, StreamingResponse, EventSourceResponse):
            continue
        assert route.response_model is not None, route.path


def test_routes_delegate_business_transactions_and_use_typed_dependencies():
    root = Path(__file__).resolve().parents[1] / "app/api/routes"
    for path in root.glob("*.py"):
        if path.name == "configuration_summary.py":
            continue  # The fixed shell count is intentionally a local, read-only aggregate.
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module == "sqlalchemy.exc" or not module.startswith("sqlalchemy"), path
            if isinstance(node, ast.Attribute):
                assert node.attr != "transaction", path
                assert not (
                    node.attr == "state"
                    and isinstance(node.value, ast.Attribute)
                    and node.value.attr == "app"
                ), path
