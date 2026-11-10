import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from uvicorn.importer import import_from_string

from app import __version__
from app.bootstrap.app import create_app
from app.infrastructure.database.session import Database
from app.resources.files.cleanup import FileCleanup
from app.resources.knowledge.worker import KnowledgeWorker
from app.resources.mcp.invocation import ToolInvocationService


def test_asgi_entrypoint_starts_without_model_configuration(monkeypatch, migrated_config):
    directory = Path(migrated_config.database.url.database).parent
    # app.main读取真实环境配置；临时数据库不足以隔离.env中的文件根目录。
    monkeypatch.setenv("APP_DATA_DIR", str(directory))
    monkeypatch.setenv("FILES_DIRECTORY", str(directory / "files"))
    monkeypatch.setenv("KNOWLEDGE_VECTOR_DIR", str(directory / "knowledge-vectors"))
    monkeypatch.setenv("SKILL_STORAGE_DIR", str(directory / "skill-assets"))
    monkeypatch.setenv("SKILL_LIBRARY_DIR", str(directory / "skill-library"))
    monkeypatch.setenv("MODEL_CONNECTIONS_KEY_FILE", str(migrated_config.model_encryption_key_file))
    monkeypatch.setenv("RUNNER_LOCK_FILE", str(migrated_config.runner_lock_file))
    with TestClient(import_from_string("app.main:app")) as client:
        assert client.app.state.files.storage.directory == directory / "files"
        assert client.app.state.knowledge_vectors.store.directory == directory / "knowledge-vectors"
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "service": "backend",
            "version": __version__,
        }
        schema = client.get("/openapi.json").json()
        assert schema["info"]["title"] == "NiumaCrew Platform API"
        assert set(schema["paths"]) == {
            "/health",
            "/api/capabilities",
            "/api/evaluations",
            "/api/evaluations/suites",
            "/api/evaluations/{batch_id}",
            "/api/evaluations/{batch_id}/cancel",
            "/api/evaluations/{batch_id}/cases/{case_id}/trace",
            "/api/evaluations/{batch_id}/cases/{case_id}/trace/actions/{action_id}/evidence/{direction}",
            "/api/conversations/{id}/trace",
            "/api/conversations/{id}/responses/{response_id}/trace",
            "/api/conversations/{id}/responses/{response_id}/trace/actions/{action_id}/evidence/{direction}",
            "/api/knowledge-bases",
            "/api/knowledge-bases/embedding-connections",
            "/api/runs/{run_id}/knowledge-evidence",
            "/api/runs/{run_id}/knowledge-evidence/{evidence_id}",
            "/api/knowledge-bases/{kb_id}/vector-index",
            "/api/knowledge-bases/{kb_id}",
            "/api/knowledge-bases/{kb_id}/documents",
            "/api/knowledge-bases/{kb_id}/documents/{document_id}",
            "/api/knowledge-bases/{kb_id}/documents/{document_id}/original",
            "/api/knowledge-bases/{kb_id}/documents/{document_id}/preview",
            "/api/knowledge-bases/{kb_id}/documents/{document_id}/chunks/{chunk_id}",
            "/api/knowledge-bases/{kb_id}/search",
            "/api/knowledge-bases/{kb_id}/demo-import",
            "/api/knowledge-bases/{kb_id}/processing",
            "/api/knowledge-bases/{kb_id}/processing/{batch_id}",
            "/api/knowledge-bases/{kb_id}/processing/{batch_id}/cancel",
            "/api/mcp-services",
            "/api/mcp-services/{id}",
            "/api/mcp-config/preview",
            "/api/tool-capabilities",
            "/api/tool-connections/{id}/annotations",
            "/api/tool-connections/{id}/discard",
            "/api/agents/{id}/usage",
            "/ready",
            "/api/configuration-summary",
            "/api/public/configuration-summary",
            "/api/conversations",
            "/api/conversations/stats",
            "/api/conversations/{id}/messages",
            "/api/conversations/{id}/questions",
            "/api/conversations/{id}/questions/{question_id}/preview",
            "/api/conversations/{id}/snapshot",
            "/api/conversations/{id}/requests/{request_id}",
            "/api/conversations/requests/{request_id}",
            "/api/conversations/{id}/responses/{response_id}",
            "/api/conversations/{id}/responses/{response_id}/events",
            "/api/conversations/{id}/responses/{response_id}/stop",
            "/api/conversations/{id}/responses/{response_id}/retry",
            "/api/organization-rules",
            "/api/model-presets",
            "/api/model-connections",
            "/api/model-connections/{connection_id}",
            "/api/model-connections/{connection_id}/test",
            "/api/auth/login",
            "/api/auth/providers",
            "/api/auth/github",
            "/api/auth/guest",
            "/api/auth/me",
            "/api/auth/logout",
            "/api/public/agents",
            "/api/public/agents/{agent_id}",
            "/api/public/skills",
            "/api/public/skills/{skill_id}",
            "/api/agents",
            "/api/tool-connections",
            "/api/tool-connections/{id}",
            "/api/tool-connections/{id}/discover",
            "/api/tool-connections/{id}/approve",
            "/api/tool-connections/{id}/oauth/sessions",
            "/api/tool-connections/{id}/oauth/sessions/{session_id}",
            "/api/tool-connections/{id}/oauth/disconnect",
            "/api/files",
            "/api/conversations/{conversation_id}/files",
            "/api/conversations/{conversation_id}/files/{file_id}",
            "/api/agents/{agent_id}",
            "/api/skills",
            "/api/skills/library",
            "/api/skills/sync",
            "/api/skills/{skill_id}",
            "/api/skills/import/preview",
            "/api/skills/import",
            "/api/skills/{skill_id}/files",
            "/api/skills/{skill_id}/export",
        }


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
    # dispose 会替换连接池并释放闲置连接。
    assert database.engine.pool is not pool
    assert not app_config.model_encryption_key_file.exists()
    assert not app_config.runner_lock_file.exists()


@pytest.mark.parametrize(
    "failure", ["tool_close", "construction", "run_worker_start", "file_start", "multiple_closes"]
)
def test_lifespan_releases_created_resources_despite_failures(app_config, monkeypatch, failure):
    from app.resources.environments.service import SandboxService
    from app.runtime.execution.scheduler import RunWorker

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

        monkeypatch.setattr("app.bootstrap.services.FileService", broken_files)
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
    processing = api_client.app.state.knowledge_processing

    def fail():
        raise RuntimeError("worker_failed")

    monkeypatch.setattr(processing, "run_next", fail)

    async def run():
        path = tmp_path / "knowledge.lock"
        worker = KnowledgeWorker(
            processing, path, reconcile=api_client.app.state.knowledge_vectors.reconcile
        )
        await worker.start()
        assert worker.task is not None
        with pytest.raises(RuntimeError, match="worker_failed"):
            await worker.task
        with pytest.raises(RuntimeError, match="worker_failed"):
            await worker.stop()
        assert worker.lock is None
        # 另一个宿主须能取得同一系统锁，而非仅清空内存字段。
        monkeypatch.setattr(processing, "run_next", lambda: False)
        replacement = KnowledgeWorker(
            processing, path, reconcile=api_client.app.state.knowledge_vectors.reconcile
        )
        await replacement.start()
        await replacement.stop()

    asyncio.run(run())
