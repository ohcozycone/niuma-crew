"""The platform starts independently of model credentials and legacy services."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from uvicorn.importer import import_from_string

from app import __version__
from app.bootstrap import create_app
from app.files.cleanup import FileCleanup
from app.infrastructure.database.session import Database
from app.knowledge.worker import KnowledgeWorker
from app.mcp.invocation import ToolInvocationService


def test_asgi_entrypoint_starts_without_model_configuration(monkeypatch, migrated_config):
    monkeypatch.setenv("MODEL_CONNECTIONS_KEY_FILE", str(migrated_config.model_encryption_key_file))
    monkeypatch.setenv("RUNNER_LOCK_FILE", str(migrated_config.runner_lock_file))
    with TestClient(import_from_string("app.main:app")) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "service": "backend",
            "version": __version__,
        }
        schema = client.get("/openapi.json").json()
        assert schema["info"]["title"] == "NiumaCrew Platform API"
        # Startup checks required entry points; each domain tests its own API contract.
        assert {
            "/health",
            "/ready",
            "/api/auth/login",
            "/api/auth/guest",
            "/api/public/agents",
            "/api/conversations",
            "/api/skills",
            "/api/knowledge-bases",
            "/api/evaluations",
        } <= schema["paths"].keys()


def test_legacy_answer_endpoint_is_removed(client):
    response = client.post("/travel-expense/answers", json={"question": "报销需要哪些材料？"})
    assert response.status_code == 404


def test_app_owns_database_lifecycle_without_running_migrations(app_config):
    app = create_app(app_config)
    assert not Path(app_config.database.url.database).exists()
    with TestClient(app):
        database = app.state.database
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
            assert (
                connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).all()
                == []
            )
        pool = database.engine.pool
    # dispose() replaces the pool and releases the application's idle connections.
    assert database.engine.pool is not pool
    assert not app_config.model_encryption_key_file.exists()
    assert not app_config.runner_lock_file.exists()


@pytest.mark.parametrize(
    "failure", ["tool_close", "construction", "run_worker_start", "file_start", "multiple_closes"]
)
def test_lifespan_releases_created_resources_despite_failures(app_config, monkeypatch, failure):
    from app.environments.service import SandboxService
    from app.execution.runtime.worker import RunWorker

    events = []
    original_close = Database.close

    def close_database(self):
        events.append("database")
        original_close(self)

    async def close_tools(self):
        events.append("tools")
        if failure in {"tool_close", "multiple_closes"}:
            raise RuntimeError("tool_close")

    monkeypatch.setattr(Database, "close", close_database)
    monkeypatch.setattr(ToolInvocationService, "close", close_tools)
    if failure == "construction":

        def broken_files(*args):
            raise RuntimeError("construction")

        monkeypatch.setattr("app.bootstrap.FileService", broken_files)
    else:
        for cls, name in (
            (RunWorker, "run_worker"),
            (KnowledgeWorker, "knowledge"),
            (SandboxService, "sandboxes"),
            (FileCleanup, "files"),
        ):

            def callbacks(label):
                async def start(self, *args):
                    if failure == f"{label}_start" or (
                        failure == "file_start" and label == "files"
                    ):
                        raise RuntimeError(failure)

                async def stop(self):
                    events.append(label)
                    if failure == "multiple_closes" and label == "knowledge":
                        raise ValueError("knowledge_close")

                return start, stop

            start, stop = callbacks(name)
            monkeypatch.setattr(cls, "start", start)
            monkeypatch.setattr(cls, "stop", stop)

    config = replace(app_config, runtime=replace(app_config.runtime, enabled=True))
    app = create_app(config)

    async def run():
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(RuntimeError) as raised:
        asyncio.run(run())
    if failure == "construction":
        assert events == ["tools", "database"]
    elif failure == "run_worker_start":
        assert events == ["run_worker", "tools", "database"]
    else:
        assert events == ["knowledge", "run_worker", "files", "sandboxes", "tools", "database"]
    if failure == "multiple_closes":
        assert str(raised.value) == "tool_close"
        assert isinstance(raised.value.__context__, ValueError)
        assert str(raised.value.__context__) == "knowledge_close"


def test_knowledge_worker_failure_releases_process_lock(api_client, tmp_path, monkeypatch):
    processing = api_client.app.state.knowledge.processing

    def fail():
        raise RuntimeError("worker_failed")

    monkeypatch.setattr(processing, "run_next", fail)

    async def run():
        path = tmp_path / "knowledge.lock"
        worker = KnowledgeWorker(processing, path)
        await worker.start()
        assert worker.task is not None
        with pytest.raises(RuntimeError, match="worker_failed"):
            await worker.task
        with pytest.raises(RuntimeError, match="worker_failed"):
            await worker.stop()
        assert worker.lock is None
        # A second worker must acquire the same OS lock, not merely see a cleared field.
        monkeypatch.setattr(processing, "run_next", lambda: False)
        replacement = KnowledgeWorker(processing, path)
        await replacement.start()
        await replacement.stop()

    asyncio.run(run())
