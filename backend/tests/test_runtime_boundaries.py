"""Both sides of the runtime boundary can operate independently."""

import ast
import asyncio
from pathlib import Path

import pytest
from runtime_helpers import MemoryControl
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from test_capability_runtime import ScriptedModel, response, setup, submit

from app.agent_runtime.checkpoints import CheckpointStore
from app.agent_runtime.contracts import AgentRequest
from app.agent_runtime.langchain import execute_agent
from app.execution.control import RunControl
from app.execution.models import Run, RunAction


def test_real_sdk_runs_with_memory_control_and_its_own_checkpoint_store(
    api_client, monkeypatch, tmp_path
):
    skill, _, _, conversation = setup(api_client)
    accepted = submit(api_client, conversation).json()
    row, messages = api_client.app.state.execution_store.load(accepted["id"])
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": "read_file",
                        "id": "one",
                        "args": {"file_path": f"/skills/s-{skill['id']}/SKILL.md"},
                    }
                ],
            ),
            response("独立完成"),
        ]
    )
    monkeypatch.setattr("app.llm.factory.create_chat_model", lambda *args, **kwargs: model)
    config = api_client.app.state.model_connections.resolve(row.config_snapshot["connection_id"])
    control = MemoryControl()
    input = AgentRequest(row.id, row.config_snapshot, messages, config)
    result = asyncio.run(
        execute_agent(input, control, checkpoints=CheckpointStore(str(tmp_path / "sdk.db")))
    )
    assert result.text == "独立完成" and control.model_calls == 2
    assert control.references and all(
        action["status"] == "succeeded" for action in control.actions.values()
    )
    assert not hasattr(control, "store") and not hasattr(control, "database")
    with api_client.app.state.database.transaction() as db:
        assert db.get(Run, row.id).status == "queued"
        assert db.scalar(select(func.count()).select_from(RunAction)) == 0


def test_atomic_model_start_rolls_back_budget_when_recording_fails(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    accepted = submit(api_client, conversation).json()
    store = api_client.app.state.execution_store
    store.claim(accepted["id"])
    control = RunControl(accepted["id"], store, lambda active, db=None: None)

    def fail(*args, **kwargs):
        raise OperationalError("injected", {}, Exception("injected"))

    monkeypatch.setattr(store, "_start_action", fail)
    with pytest.raises(OperationalError):
        asyncio.run(control.start_model())
    with api_client.app.state.database.transaction() as db:
        assert db.get(Run, accepted["id"]).model_calls == 0
        assert db.scalar(select(func.count()).select_from(RunAction)) == 0


def test_dependency_directions_prevent_sdk_and_application_state_leaks():
    root = Path(__file__).resolve().parents[1] / "app"
    rules = {
        "agent_runtime": (
            "app.api",
            "app.auth",
            "app.execution",
            "app.agents",
            "app.conversations",
            "sqlalchemy",
        ),
        "execution": (
            "app.api",
            "app.conversations",
            "app.ci_diagnosis",
            "langchain",
            "langchain_core",
            "langgraph",
            "deepagents",
        ),
        "conversations": ("app.api", "fastapi"),
        "capability_catalog": ("app.api", "fastapi", "app.execution", "app.agent_runtime"),
        "tools": ("app.api", "app.conversations", "app.execution", "app.agents"),
        "files": (
            "app.api",
            "app.conversations",
            "app.execution",
            "app.agents",
            "langchain",
            "deepagents",
        ),
        "sandboxes": (
            "app.api",
            "app.conversations",
            "app.execution",
            "app.agents",
            "langchain",
            "deepagents",
        ),
    }
    for directory, forbidden in rules.items():
        for path in (root / directory).rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                modules = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else [item.name for item in node.names]
                    if isinstance(node, ast.Import)
                    else []
                )
                assert not any(
                    module == prefix or module.startswith(prefix + ".")
                    for module in modules
                    for prefix in forbidden
                ), path
            if directory == "agent_runtime":
                assert not any(
                    isinstance(node, ast.Attribute)
                    and node.attr in ("store", "_store", "database", "auth")
                    for node in ast.walk(tree)
                ), path
