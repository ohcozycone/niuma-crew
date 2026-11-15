"""恢复由改造前快照源码生成的中断运行，样本仅含合成账号和资料。"""

import asyncio
import json
import sqlite3
import tarfile
from datetime import timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from checkpoint_worker import CheckpointModel
from fastapi.testclient import TestClient
from langchain_core.messages import ToolMessage
from run_helpers import execute_run, read_reply
from sqlalchemy import select

from app.auth.models import AuthSession
from app.bootstrap.app import create_app
from app.common.values import utc_now
from app.runtime.execution.models import Run, RunAction


def test_snapshot_version_eight_checkpoint_resumes_without_replaying_saved_tool(
    app_config, tmp_path, monkeypatch
):
    fixture = Path(__file__).with_name("fixtures") / "backend_boundary_v8.tar.gz"
    with tarfile.open(fixture) as archive:
        archive.extractall(tmp_path, filter="data")
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["source_commit"] == "b2cacbd61a02ec7e11e84507a25504ecf42c4b9e"
    # Run current additive schema migrations as deployment would; never rewrite the fixture
    # checkpoint or its historical Run snapshot to manufacture compatibility.
    with sqlite3.connect(app_config.database.url.database) as db:
        original = db.execute(
            "SELECT config_snapshot FROM runs WHERE id=?", (saved["run_id"],)
        ).fetchone()
    monkeypatch.setenv(
        "DATABASE_URL", app_config.database.url.render_as_string(hide_password=False)
    )
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    with sqlite3.connect(app_config.database.url.database) as db:
        assert (
            db.execute("SELECT config_snapshot FROM runs WHERE id=?", (saved["run_id"],)).fetchone()
            == original
        )

    class Continuation(CheckpointModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            assert isinstance(messages[-1], ToolMessage)
            return super()._generate(messages, stop, run_manager, **kwargs)

    monkeypatch.setattr(
        "app.infrastructure.llm.factory.create_chat_model",
        lambda *args, **kwargs: Continuation(path="unused-on-resume"),
    )
    with TestClient(create_app(app_config), headers={"Origin": "http://localhost:3000"}) as client:
        # 仅刷新合成样本的授权和执行时钟，保证长期回归不受样本过期影响。
        # SDK 存档、Run 配置、输入、动作和用量保持原版本字节与事实。
        now = utc_now()
        with client.app.state.database.transaction() as db:
            for session in db.scalars(select(AuthSession)):
                session.created_at = session.last_seen_at = now
                session.expires_at = now + timedelta(days=1)
            row = db.get(Run, saved["run_id"])
            assert row.status == "running" and row.model_calls == 2
            row.started_at = now
        client.cookies.update(saved["cookies"])
        assert client.app.state.run_worker.store.recover(resume=True) == []
        asyncio.run(execute_run(client, saved["run_id"]))
        client.app.state.conversation_acceptance.process(saved["run_id"])
        result = read_reply(client, saved["run_id"])
        assert result["status"] == "succeeded" and result["content"] == "回答一"
        assert result["acceptance"] == "accepted"
        with client.app.state.database.transaction() as db:
            row = db.get(Run, saved["run_id"])
            tools = list(
                db.scalars(
                    select(RunAction).where(
                        RunAction.run_id == row.id, RunAction.kind == "tool_call"
                    )
                )
            )
            models = list(
                db.scalars(
                    select(RunAction)
                    .where(RunAction.run_id == row.id, RunAction.kind == "model_call")
                    .order_by(RunAction.sequence)
                )
            )
            assert len(tools) == 1 and tools[0].status == "succeeded"
            assert row.model_calls == len(models) == 3 and models[1].status == "unknown"
            assert row.usage is not None and row.usage["total_tokens"] is None
