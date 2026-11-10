import ast
import asyncio
from importlib.util import resolve_name
from pathlib import Path

import pytest
from runtime_helpers import MemoryContext, make_task
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from test_capability_runtime import ScriptedModel, response, setup, submit

from app.agent.checkpoints import CheckpointStore
from app.agent.contracts import AgentRequest
from app.agent.engine import execute_agent
from app.execution.models import Run, RunAction


def test_real_sdk_runs_with_memory_control_and_its_own_checkpoint_store(
    api_client, monkeypatch, tmp_path
):
    skill, _, _, conversation = setup(api_client)
    accepted = submit(api_client, conversation).json()["response"]
    row, messages = api_client.app.state.run_worker.store.load(accepted["id"])
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
    control = MemoryContext()
    input = AgentRequest(row.id, row.config_snapshot, messages, config, thread_id=row.thread_id)
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
    accepted = submit(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    store.claim(accepted["id"])
    control = make_task(accepted["id"], store, lambda active, db=None: None)

    def fail(*args, **kwargs):
        raise OperationalError("injected", {}, Exception("injected"))

    monkeypatch.setattr(store, "_start_action", fail)
    with pytest.raises(OperationalError):
        asyncio.run(
            control.start_model(
                {
                    "catalog_hash": control.row.config_snapshot["tool_catalog"]["catalog_hash"],
                    "exposed_tool_ids": [],
                }
            )
        )
    with api_client.app.state.database.transaction() as db:
        assert db.get(Run, accepted["id"]).model_calls == 0
        assert db.scalar(select(func.count()).select_from(RunAction)) == 0


def imported_modules(source: str, package: str) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = resolve_name("." * node.level + module, package)
            modules.add(module)
            modules.update(f"{module}.{item.name}" for item in node.names)
    return modules


@pytest.mark.parametrize(
    "source,package,expected",
    [
        ("import app.bootstrap as setup", "app.api", "app.bootstrap"),
        ("from app import bootstrap", "app.api", "app.bootstrap"),
        ("from .. import bootstrap", "app.api", "app.bootstrap"),
        ("from ..auth import service", "app.llm", "app.auth.service"),
        ("from app.infrastructure import database", "app.llm", "app.infrastructure.database"),
    ],
)
def test_import_guard_resolves_aliases_package_imports_and_relative_imports(
    source, package, expected
):
    assert expected in imported_modules(source, package)


def test_dependency_directions_prevent_sdk_and_application_state_leaks():
    root = Path(__file__).resolve().parents[1] / "app"
    sdk_packages = ("langchain", "langchain_core", "langgraph", "deepagents")
    persistence_forbidden = (
        "app.api",
        "app.conversations",
        "app.agent.engine",
        "app.execution.snapshot",
        "app.agent.prompts",
        "app.agent.model_calls",
        "app.agent.tool_calls",
        "app.agent.skills",
        "app.builtin_tools.workspace",
        "app.agent.checkpoints",
        "app.agent.streaming",
        "app.agent.config",
        *sdk_packages,
    )
    rules = {
        "evaluations": (
            "app.api",
            "app.conversations",
            "app.agent.engine",
            "fastapi",
            *sdk_packages,
        ),
        "execution": (
            "app.api",
            "app.conversations",
            "app.evaluations",
            "app.public_errors",
            "fastapi",
            *sdk_packages,
        ),
        "execution/models.py": persistence_forbidden,
        "execution/store.py": persistence_forbidden,
        "builtin_tools": (
            "app.agent",
            "app.execution",
            "app.employees",
            "app.auth",
            "sqlalchemy",
            "fastapi",
        ),
        "agent": (
            "app.public_errors",
            "app.api",
            "app.auth",
            "app.employees",
            "app.execution",
            "app.conversations",
            "sqlalchemy",
            "fastapi",
        ),
        "agent/prompts.py": ("app", "sqlalchemy", *sdk_packages),
        "execution/snapshot.py": ("app.api", "app.conversations", *sdk_packages),
        "infrastructure/concurrency.py": ("app", "sqlalchemy", *sdk_packages),
        "infrastructure/settings.py": ("app", "sqlalchemy", *sdk_packages),
        "conversations": ("app.api", "fastapi"),
        "capability_catalog": ("app.api", "fastapi", "app.execution", "app.agent"),
        "mcp": ("app.api", "app.conversations", "app.execution", "app.agent", "app.employees"),
        "files": (
            "app.api",
            "app.conversations",
            "app.execution",
            "app.agent",
            "app.employees",
            *sdk_packages,
        ),
        "environments": (
            "app.api",
            "app.conversations",
            "app.execution",
            "app.agent",
            "app.employees",
            *sdk_packages,
        ),
        "llm": (
            "app.api",
            "app.auth",
            "app.employees",
            "app.conversations",
            "app.execution",
            "app.agent",
            "app.model_connections",
            "app.knowledge",
            "app.skills",
            "app.mcp",
            "app.files",
            "app.environments",
            "app.organization_rules",
            "app.capability_catalog",
            "app.infrastructure.database",
            "app.bootstrap",
            "app.main",
            "sqlalchemy",
        ),
        "api": ("app.bootstrap", "app.main"),
    }
    for directory, forbidden in rules.items():
        target = root / directory
        paths = [target] if target.is_file() else list(target.rglob("*.py"))
        assert paths, f"Import guard has no source files: {directory}"
        for path in paths:
            source = path.read_text()
            package = ".".join(("app", *path.relative_to(root).parent.parts))
            effective_forbidden = forbidden
            modules = imported_modules(source, package)
            assert not any(
                module == prefix or module.startswith(prefix + ".")
                for module in modules
                for prefix in effective_forbidden
            ), path
            if directory == "agent":
                tree = ast.parse(source)
                assert not any(
                    isinstance(node, ast.Attribute)
                    and node.attr in ("store", "_store", "database", "auth")
                    for node in ast.walk(tree)
                ), path
