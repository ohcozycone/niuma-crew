"""Trusted SDK stdio sessions: real processes, account boundary and cleanup."""

import asyncio
import json
import os
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.mcp.adapters.stdio import StdioMCPClient
from app.mcp.config import ToolConfig
from app.values import digest


@pytest.mark.anyio
async def test_sandbox_release_failure_still_closes_run_mcp_caller():
    from app.execution.contracts import AgentOutput
    from app.execution.runtime.task import RunTask

    closed = []

    class Caller:
        async def aclose(self):
            closed.append("mcp-closed")

    def fail_release():
        raise RuntimeError("injected sandbox cleanup failure")

    async def execute_agent(*args, **kwargs):
        return AgentOutput("done")

    row = SimpleNamespace(
        id="run",
        thread_id="run",
        checkpoint_id=None,
        base_checkpoint_id=None,
        base_run_id=None,
        input_snapshot=[],
        model_calls=0,
        owner_user_id="owner",
        config_snapshot={
            "schema_version": 5,
            "summary_trigger_tokens": 100,
            "summary_keep_tokens": 20,
            "memory_scope": "test",
            "memory_reset": False,
            "agent_id": "employee",
            "connection_id": "model",
            "connection_config_revision": 1,
            "connection_credential_revision": 1,
            "system_prompt": "Work within the granted workspace.",
            "skills": [],
            "selected_skill_ids": [],
            "recursion_limit": 10,
            "max_model_calls": 3,
            "max_skill_reads": 3,
            "max_output_tokens": 100,
            "max_output_bytes": 1000,
            "max_reasoning_bytes": 1000,
            "context_bytes": 1000,
            "run_timeout": 30,
            "workspace": {"mode": "sandbox"},
        },
    )
    context = RunTask(
        row.id,
        None,
        settings=None,
        agent=None,
        store=SimpleNamespace(
            load=lambda _: (row, []),
            restore_control=lambda run_id: {"active_skills": set(), "contents": [], "usage": None},
        ),
        runs=None,
        connections=SimpleNamespace(resolve=lambda *args: None),
        checkpoints=SimpleNamespace(for_run=lambda *args, **kwargs: None),
        tools=SimpleNamespace(for_run=lambda run_id: Caller()),
        files=SimpleNamespace(
            read=lambda id: b"", sources=lambda id: [], save=lambda *args, **kwargs: {}
        ),
        sandboxes=SimpleNamespace(for_run=lambda *args: SimpleNamespace(release=fail_release)),
        skills=None,
        knowledge=None,
    )
    with pytest.raises(RuntimeError, match="injected sandbox cleanup failure"):
        async with context:
            pass
    assert closed == ["mcp-closed"]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def stdio_server(tmp_path):
    path = tmp_path / "server.py"
    path.write_text("""
import os
import subprocess
import sys
from fastmcp import FastMCP
helper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
with open(os.environ["PID_FILE"], "w") as output:
    output.write(f"{os.getpid()} {helper.pid}")
server = FastMCP("fixture", instructions="Fixture account instructions")
@server.tool
def inspect_context() -> dict:
    return {"pid": os.getpid(), "token": os.environ.get("FIXTURE_TOKEN"), "cwd": os.getcwd(), "application_key": os.environ.get("MODEL_CONNECTIONS_ENCRYPTION_KEY")}
server.run(show_banner=False)
""")
    return path


def process_running(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.anyio
async def test_stdio_sdk_reuses_run_process_and_reaps_helper(stdio_server, tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CONNECTIONS_ENCRYPTION_KEY", "host-key-must-not-inherit")
    pid_file = tmp_path / "pids"
    client = StdioMCPClient(
        {"command": sys.executable, "args": [str(stdio_server)]},
        {"PID_FILE": str(pid_file), "FIXTURE_TOKEN": "account-fixture-secret"},
        ToolConfig(stdio_enabled=True),
        asyncio.Semaphore(1),
    )
    try:
        catalog = await client.discover()
        assert client.instructions == "Fixture account instructions"

        async def guard():
            pass

        first = await client.invoke("inspect_context", {}, catalog[0]["descriptor_hash"], guard)
        second = await client.invoke("inspect_context", {}, catalog[0]["descriptor_hash"], guard)
        assert first[0][0]["text"] == second[0][0]["text"]
        assert "account-fixture-secret" in json.dumps(first)
        assert "host-key-must-not-inherit" not in json.dumps(first)
        server_pid, helper_pid = map(int, pid_file.read_text().split())
        assert process_running(server_pid) and process_running(helper_pid)
        client.expected_instructions_hash = digest("not-approved-guidance")
        with pytest.raises(Exception) as changed:
            await client.invoke("inspect_context", {}, catalog[0]["descriptor_hash"], guard)
        assert changed.value.code == "tool_catalog_changed"
    finally:
        await client.aclose()
    assert not process_running(server_pid)
    assert not process_running(helper_pid)
    with pytest.raises(Exception) as closed:
        await client.discover()
    assert closed.value.code == "stdio_session_closed"
    assert not process_running(server_pid)


@pytest.mark.anyio
async def test_stdio_capacity_wait_and_cancellation_cleanup(stdio_server, tmp_path):
    limiter = asyncio.Semaphore(1)
    first = StdioMCPClient(
        {"command": sys.executable, "args": [str(stdio_server)]},
        {"PID_FILE": str(tmp_path / "first")},
        ToolConfig(stdio_enabled=True),
        limiter,
    )
    second = StdioMCPClient(
        {"command": sys.executable, "args": [str(stdio_server)]},
        {"PID_FILE": str(tmp_path / "second")},
        ToolConfig(stdio_enabled=True, stdio_wait_seconds=0.05),
        limiter,
    )
    try:
        await first.discover()
        with pytest.raises(Exception) as error:
            await second.discover()
        assert error.value.code == "stdio_capacity_exhausted"
        assert not (tmp_path / "second").exists()
    finally:
        await first.aclose()
        await second.aclose()
    assert limiter._value == 1
    third = StdioMCPClient(
        {"command": sys.executable, "args": ["-c", "import time; time.sleep(300)"]},
        {},
        ToolConfig(stdio_enabled=True),
        limiter,
    )
    task = asyncio.create_task(third.discover())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await third.aclose()
    assert limiter._value == 1


def enable_stdio(client):
    client.app.state.tool_connections.config = replace(
        client.app.state.tool_connections.config, stdio_enabled=True
    )
    client.app.state.mcp_definitions.config = client.app.state.tool_connections.config


def test_stdio_registration_is_admin_only_and_import_is_inert(api_client):
    enable_stdio(api_client)
    configuration = {
        "mcpServers": {
            "example": {
                "command": "npx",
                "args": ["-y", "example-mcp@1.0.0"],
                "env": {"API_KEY": "import-secret"},
            }
        }
    }
    preview = api_client.post(
        "/api/mcp-config/preview", json={"configuration": json.dumps(configuration)}
    )
    assert preview.status_code == 200, preview.text
    assert "import-secret" not in preview.text
    entry = preview.json()["entries"][0]
    assert entry["env_keys"] == ["API_KEY"]
    for empty in ("", "${API_KEY}", "{{API_KEY}}"):
        configuration["mcpServers"]["example"]["env"]["API_KEY"] = empty
        pending = api_client.post(
            "/api/mcp-config/preview", json={"configuration": json.dumps(configuration)}
        )
        assert pending.status_code == 200, pending.text
        assert pending.json()["entries"][0]["env_keys"] == ["API_KEY"]
        assert not pending.json()["entries"][0]["has_credential"]
    definition = {
        "name": "Trusted fixture",
        "transport": "stdio",
        "command": sys.executable,
        "args": [],
        "env_keys": ["API_KEY"],
    }
    created = api_client.post("/api/mcp-services", json=definition)
    assert created.status_code == 201, created.text
    from test_mcp_accounts import member

    member(api_client)
    denied = api_client.post("/api/mcp-services", json=definition)
    assert denied.status_code == 403, denied.text
    service = created.json()
    connection = api_client.post(
        "/api/tool-connections",
        json={
            "name": "Own env",
            "service_id": service["id"],
            "kind": "mcp_stdio",
            "auth_type": "env",
            "public_config": {key: service[key] for key in ("command", "args", "env_keys")},
            "environment": {"API_KEY": "personal fixture secret"},
        },
    )
    assert connection.status_code == 201, connection.text
    assert connection.json()["has_credential"]
    assert "personal fixture secret" not in connection.text
    changed = api_client.patch(
        f"/api/tool-connections/{connection.json()['id']}",
        json={
            "expected_config_revision": 1,
            "expected_credential_revision": 1,
            "public_config": {
                "command": "sh",
                "args": ["-c", "echo denied"],
                "env_keys": ["API_KEY"],
            },
        },
    )
    assert changed.status_code == 422, changed.text


def test_stdio_disabled_by_deployer_and_no_unregistered_execution(api_client):
    response = api_client.post(
        "/api/mcp-services", json={"name": "disabled", "transport": "stdio", "command": "npx"}
    )
    assert response.status_code == 422 and response.json()["detail"]["code"] == "stdio_disabled"
    enable_stdio(api_client)
    response = api_client.post(
        "/api/tool-connections",
        json={
            "name": "unregistered",
            "kind": "mcp_stdio",
            "public_config": {"command": "npx", "args": [], "env_keys": []},
        },
    )
    assert (
        response.status_code == 422 and response.json()["detail"]["code"] == "mcp_service_invalid"
    )


@pytest.mark.parametrize(
    "key",
    [
        "PATH",
        "PYTHONPATH",
        "NODE_OPTIONS",
        "DYLD_INSERT_LIBRARIES",
        "LD_PRELOAD",
        "HOME",
        "BASH_ENV",
        "npm_config_script_shell",
        "JAVA_TOOL_OPTIONS",
        "HTTP_PROXY",
    ],
)
def test_stdio_cannot_turn_account_environment_into_runtime_injection(api_client, key):
    enable_stdio(api_client)
    response = api_client.post(
        "/api/mcp-services",
        json={
            "name": "rejected",
            "transport": "stdio",
            "command": sys.executable,
            "env_keys": [key],
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "stdio_environment_denied"


def test_stdio_account_catalog_snapshot_and_run_caller_are_integrated(
    api_client, stdio_server, tmp_path
):
    from test_capability_runtime import setup

    from app.employees.assembly import capture_tools

    enable_stdio(api_client)
    _, _, agent, _ = setup(api_client)
    definition = api_client.post(
        "/api/mcp-services",
        json={
            "name": "Process fixture",
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(stdio_server)],
            "env_keys": ["PID_FILE", "FIXTURE_TOKEN"],
        },
    )
    assert definition.status_code == 201, definition.text
    service = definition.json()
    token = "integration-fixture-secret"
    connection = api_client.post(
        "/api/tool-connections",
        json={
            "name": "Process account",
            "kind": "mcp_stdio",
            "service_id": service["id"],
            "auth_type": "env",
            "public_config": {key: service[key] for key in ("command", "args", "env_keys")},
            "environment": {"PID_FILE": str(tmp_path / "integration-pids"), "FIXTURE_TOKEN": token},
        },
    )
    assert connection.status_code == 201, connection.text
    row = connection.json()
    discovered = api_client.post(f"/api/tool-connections/{row['id']}/discover")
    assert discovered.status_code == 200, discovered.text
    candidate = discovered.json()
    assert candidate["discovery_candidate"]["instructions"] == "Fixture account instructions"
    approved = api_client.post(
        f"/api/tool-connections/{row['id']}/approve",
        json={
            "expected_config_revision": row["config_revision"],
            "expected_catalog_revision": row["catalog_revision"],
            "candidate_hash": candidate["discovery_candidate"]["hash"],
        },
    )
    assert approved.status_code == 200, approved.text
    account = approved.json()
    assert account["approved_instructions"] == "Fixture account instructions"
    assigned = api_client.patch(
        f"/api/agents/{agent['id']}",
        json={
            "expected_revision": agent["revision"],
            "tool_grants": [
                {
                    "connection_id": row["id"],
                    "tools": ["inspect_context"],
                    "expected_descriptors": {
                        "inspect_context": account["approved_catalog"][0]["descriptor_hash"]
                    },
                    "scope_policy": {"mode": "provider", "max_calls": 5},
                }
            ],
        },
    )
    assert assigned.status_code == 200, assigned.text
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    with api_client.app.state.database.transaction() as db:
        bindings, _, _ = capture_tools(db, agent["id"], actor.user_id)
    assert bindings[0]["kind"] == "mcp_stdio"
    assert bindings[0]["server_instructions"] == "Fixture account instructions"
    assert token not in json.dumps(bindings)

    async def use_and_close():
        async def guard():
            pass

        tools = api_client.app.state.tool_invocation
        async with tools.for_run("fixture-run") as caller:
            first = await caller.call(bindings[0], {}, guard)
            second = await caller.call(bindings[0], {}, guard)
            assert token not in first.content and "[REDACTED]" in first.content
            assert token not in second.content
            assert len(caller.clients) == 1
        assert not tools._run_callers

    asyncio.run(use_and_close())
    assert all(
        not process_running(int(pid)) for pid in (tmp_path / "integration-pids").read_text().split()
    )
