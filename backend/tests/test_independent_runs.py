"""Independent execution, durable results and recoverable application adoption."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from langchain_core.tools import StructuredTool
from run_helpers import cancel_run, checkpoint_store, empty_conversation, execute_run, load_run
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from test_capability_runtime import ScriptedModel, response
from test_response_contract import employee

from app.bootstrap import create_app
from app.conversations.acceptance import ConversationAcceptance
from app.conversations.models import Conversation, ConversationRun, Message
from app.errors import NotFoundError, PermissionDeniedError
from app.execution.contracts import Completion
from app.execution.errors import PersistenceFailure
from app.execution.models import Run, RunAction
from app.execution.runtime.tool_calls import validate_tool_names
from app.execution.store import RunStore, require_run, retained_file_ids
from app.files.models import StoredFile
from app.infrastructure.database.transactions import reserve_writer
from app.values import utc_now


@pytest.fixture
def direct(api_client, migrated_config):
    with TestClient(
        create_app(migrated_config),
        headers={
            "Origin": "http://localhost:3000",
            "Content-Type": "application/json",
        },
    ) as client:
        client.cookies.update(api_client.cookies)
        yield client


def accept_work(client, agent):
    """测试应用直接使用内部受理能力，不为测试提供生产 HTTP 提交入口。"""
    actor = client.app.state.auth.resolve(client.cookies.get("app_session"))
    runs = client.app.state.runs
    with client.app.state.database.transaction() as db:
        reserve_writer(db, Run.__table__)
        from app.infrastructure.database.identifiers import allocate_id

        row = runs.submit(
            db,
            actor,
            owner_user_id=actor.user_id,
            agent_id=agent["id"],
            origin_kind="test",
            operation="test.accept",
            request_id=str(uuid4()),
            digest="test-input",
            content="完成工作",
            input_message_id=allocate_id(db),
            selected_skill_ids=[],
            file_ids=[],
            thread_id="test:" + str(uuid4()),
        )
        return row.id


def test_only_current_application_routes_are_exposed(direct):
    schema = direct.get("/openapi.json").json()
    assert not any(path.startswith("/api/runs") for path in schema["paths"])
    assert "/api/sandbox-status" not in schema["paths"]
    assert not any("tool-grants" in path for path in schema["paths"])
    assert "post" in schema["paths"]["/api/conversations"]
    assert "/api/conversations/{id}" not in schema["paths"]
    assert "RunSubmit" not in schema["components"]["schemas"]
    assert direct.post("/api/runs", json={}).status_code == 404


def test_task_runs_real_multiround_sdk_without_any_product_messages(direct, monkeypatch):
    agent = employee(direct)
    skill = direct.post(
        "/api/skills",
        json={
            "name": "独立方法",
            "description": "审阅规则",
            "instructions": "INDEPENDENT_BODY：核对原文。",
        },
    ).json()
    direct.patch(
        f"/api/agents/{agent['id']}",
        json={
            "expected_revision": agent["revision"],
            "skill_assignments": [{"skill_id": skill["id"]}],
        },
    )
    model = ScriptedModel(
        responses=[
            response(
                "先读方法",
                [
                    {
                        "name": "read_file",
                        "id": "read",
                        "args": {"file_path": f"/skills/s-{skill['id']}/SKILL.md"},
                    }
                ],
            ),
            response("独立成果"),
        ]
    )
    monkeypatch.setattr("app.llm.factory.create_chat_model", lambda *args, **kwargs: model)
    id = accept_work(direct, agent)
    asyncio.run(execute_run(direct, id))
    result = load_run(direct, id)
    assert result.status == "succeeded" and result.result_text == "独立成果"
    assert "INDEPENDENT_BODY" in model.prompts[1]
    assert result.model_calls == 2
    with direct.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Conversation)) == 0
        assert db.scalar(select(func.count()).select_from(Message)) == 0
        assert db.scalar(select(func.count()).select_from(ConversationRun)) == 0
        assert db.scalar(select(func.count()).select_from(Run)) == 1
    checkpoint_store(direct).path.unlink(missing_ok=True)
    assert load_run(direct, id).result_text == "独立成果"


def test_cancel_does_not_resurrect_finished_work(direct):
    agent = employee(direct)
    id = accept_work(direct, agent)
    cancel_run(direct, id)
    assert load_run(direct, id).status == "cancelled"
    direct.app.state.runs.complete(Completion(id, "迟到成果", "succeeded"))
    assert load_run(direct, id).result_text is None


def test_result_and_success_roll_back_together_on_storage_failure(direct, monkeypatch):
    id = accept_work(direct, employee(direct))

    def broken(*args, **kwargs):
        raise OperationalError("injected", {}, Exception("injected"))

    monkeypatch.setattr(RunStore, "finish", broken)
    with pytest.raises(PersistenceFailure):
        direct.app.state.runs.complete(Completion(id, "成果", "succeeded"))
    with direct.app.state.database.transaction() as db:
        row = db.get(Run, id)
        assert row.status == "queued" and row.result_text is None


def test_result_files_survive_checkpoint_and_sweep_and_remain_private(direct):
    id = accept_work(direct, employee(direct))
    with direct.app.state.database.transaction() as db:
        owner = db.get(Run, id).owner_user_id
    ref = direct.app.state.files.save(
        owner, "成果.txt", b"durable result", purpose="output", run_id=id
    )
    direct.app.state.runs.complete(
        Completion(id, "成果", "succeeded", structured={"output_files": [ref]})
    )
    with direct.app.state.database.transaction() as db:
        db.get(StoredFile, ref["id"]).created_at = utc_now() - timedelta(days=365)
    checkpoint_store(direct).path.unlink(missing_ok=True)
    direct.app.state.file_cleanup.sweep(retained_file_ids)
    assert load_run(direct, id).result_data["output_files"] == [ref]
    assert direct.app.state.files.read(ref["id"]) == b"durable result"
    actor = direct.app.state.auth.resolve(direct.cookies.get("app_session"))
    with pytest.raises(NotFoundError):
        with direct.app.state.database.transaction() as db:
            require_run(db, id, replace(actor, role="member", user_id=str(uuid4())))
    cancel_run(direct, id)
    assert load_run(direct, id).status == "succeeded"
    with pytest.raises(IntegrityError):
        with direct.app.state.database.transaction() as db:
            db.execute(update(Run).where(Run.id == id).values(result_text="覆盖"))


def test_new_application_worker_repairs_acceptance_without_reexecuting(direct, monkeypatch):
    agent = employee(direct)
    conversation = empty_conversation(direct, agent["id"])["id"]
    reply = direct.post(
        f"/api/conversations/{conversation}/messages",
        json={
            "client_request_id": str(uuid4()),
            "content": "原问题",
        },
    ).json()["response"]
    with direct.app.state.database.transaction() as db:
        id = db.scalar(select(ConversationRun.run_id).where(ConversationRun.run_id == reply["id"]))
    direct.app.state.runs.complete(Completion(id, "已完成工作", "succeeded"))
    pending = direct.get(f"/api/conversations/{conversation}/responses/{reply['id']}").json()[
        "response"
    ]
    assert pending["status"] == "succeeded" and pending["acceptance"] == "pending"
    assert pending["content"] == "已完成工作" and pending["content_state"] == "draft"

    def forbidden(*args, **kwargs):
        raise AssertionError("Application adoption must not invoke a model")

    monkeypatch.setattr("app.llm.factory.create_chat_model", forbidden)
    replacement = ConversationAcceptance(direct.app.state.database, direct.app.state.runs.authorize)
    replacement.sweep()
    done = direct.get(f"/api/conversations/{conversation}/responses/{reply['id']}").json()[
        "response"
    ]
    assert done["acceptance"] == "accepted" and done["content_state"] == "complete"
    assert done["version"] > pending["version"]
    replacement.sweep()
    with direct.app.state.database.transaction() as db:
        assert db.get(ConversationRun, id).acceptance_attempts == 1


def test_tool_registration_rejects_duplicate_names():
    def read(value: str) -> str:
        return value

    tool = StructuredTool.from_function(read, description="读取")
    with pytest.raises(Exception, match="tool_catalog_changed"):
        validate_tool_names([tool, tool])


def test_downgrade_cannot_discard_an_independent_result(direct):
    id = accept_work(direct, employee(direct))
    direct.app.state.runs.complete(Completion(id, "不可丢弃的成果", "succeeded"))
    configuration = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.raises(RuntimeError, match="不支持有损降级"):
        command.downgrade(configuration, "0018")
    assert load_run(direct, id).result_text == "不可丢弃的成果"


def test_cancellation_preserves_a_confirmed_action_outcome(direct):
    id = accept_work(direct, employee(direct))
    store = direct.app.state.run_worker.store
    assert store.claim(id)
    key = store.start_action(id, "tool:late", "tool_call")
    cancel_run(direct, id)
    assert load_run(direct, id).status == "cancelling"
    store.finish_action(id, key, "succeeded", result_payload={"content": "写入已确认"})
    direct.app.state.runs.complete(Completion(id, "迟到回复", "succeeded"))
    current = load_run(direct, id)
    assert current.status == "cancelled" and current.result_text is None
    with direct.app.state.database.transaction() as db:
        assert db.scalar(select(RunAction).where(RunAction.run_id == id)).status == "succeeded"


def test_business_rejection_releases_scope_without_changing_execution(direct):
    agent = employee(direct)
    conversation = empty_conversation(direct, agent["id"])["id"]
    accepted = direct.post(
        f"/api/conversations/{conversation}/messages",
        json={
            "client_request_id": str(uuid4()),
            "content": "原问题",
        },
    ).json()
    reply = accepted["response"]
    with direct.app.state.database.transaction() as db:
        id = db.scalar(select(ConversationRun.run_id).where(ConversationRun.run_id == reply["id"]))
    direct.app.state.runs.complete(Completion(id, "已完成工作", "succeeded"))

    def reject(*args, **kwargs):
        raise PermissionDeniedError("permission_denied", "不能再接纳此回复。")

    direct.app.state.conversation_acceptance.authorize = reject
    direct.app.state.conversation_acceptance.process(id)
    current = direct.get(f"/api/conversations/{conversation}/responses/{reply['id']}").json()
    assert current["response"]["status"] == "succeeded"
    assert current["response"]["acceptance"] == "failed"
    assert current["conversation"]["active_response_id"] is None
    assert current["conversation"]["version"] > accepted["conversation"]["version"]
    assert load_run(direct, id).result_text == "已完成工作"


def test_acceptance_shutdown_joins_the_current_database_scan(direct, monkeypatch):
    entered, release = Event(), Event()
    acceptance = direct.app.state.conversation_acceptance

    def scan():
        entered.set()
        assert release.wait(3)

    monkeypatch.setattr(acceptance, "sweep", scan)

    async def shutdown():
        await acceptance.start()
        assert await asyncio.to_thread(entered.wait, 2)
        stopping = asyncio.create_task(acceptance.stop())
        await asyncio.sleep(0.02)
        assert not stopping.done()
        release.set()
        await stopping

    try:
        asyncio.run(shutdown())
    finally:
        release.set()


@pytest.mark.parametrize(
    ("normalized", "error"), [("   ", "empty_response"), ("一二", "output_limit_exceeded")]
)
def test_final_content_validation_is_an_execution_failure(direct, monkeypatch, normalized, error):
    from configuration_helpers import set_submission_limits

    set_submission_limits(direct.app.state.conversation_commands, max_output_bytes=4)
    id = accept_work(direct, employee(direct))
    monkeypatch.setattr(direct.app.state.runs, "prepare_content", lambda db, row, text: normalized)
    direct.app.state.runs.complete(Completion(id, "好", "succeeded"))
    row = load_run(direct, id)
    assert row.status == "failed" and row.error_code == error
    assert row.result_text is None and row.result_data is None
    assert direct.app.state.runtime_status.phase == "ready"
