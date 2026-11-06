"""Product publication, execution ownership and SDK failure boundaries."""

import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from checkpoint_helpers import publication_graph
from langchain_core.messages import AIMessage, HumanMessage
from run_helpers import checkpoint_store, complete_run, execute_run, read_reply, reply_path
from sqlalchemy import func, select
from test_capability_runtime import ScriptedModel, execute, response, setup, submit
from test_conversations import send

from app.conversations.models import ConversationRun, Message
from app.execution.contracts import Completion
from app.execution.models import Run
from app.execution.runtime.checkpoints import CheckpointStore, checkpoint_config


def test_product_history_and_next_context_do_not_read_sdk_state(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation, content="原问题").json()["response"]
    done = execute(api_client, monkeypatch, ScriptedModel(responses=[response("稳定回答")]), run)
    assert done["status"] == "succeeded" and done["content"] == "稳定回答"
    store = api_client.app.state.run_worker.store
    checkpoint_store(api_client).path.unlink()

    def forbidden(*args, **kwargs):
        raise AssertionError("Product reads must not open SDK storage")

    monkeypatch.setattr(CheckpointStore, "reader", forbidden)
    base = f"/api/conversations/{conversation['id']}"
    page = api_client.get(base + "/messages").json()["items"]
    assert [item["content"] for item in page] == ["原问题", "稳定回答"]
    assert all(item["role"] == "user" or item["content_state"] == "complete" for item in page)
    assert (
        api_client.get(base + f"/questions/{run['reply_to_message_id']}/preview").json()["answer"]
        == "稳定回答"
    )
    next_run = send(api_client, conversation, "追问").json()["response"]
    row, inputs = store.load(next_run["id"])
    assert [item["content"] for item in inputs] == ["追问"]
    assert row.base_run_id == run["id"] and row.base_checkpoint_id
    assert row.checkpoint_id is None


def test_acceptance_failure_preserves_execution_result_and_retries_only_business_save(api_client):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    acceptance = api_client.app.state.conversation_acceptance
    original = acceptance.publish_content
    assert store.claim(run["id"])
    api_client.app.state.runs.complete(Completion(run["id"], "完整执行成果", "succeeded"))

    def broken(db, row, result):
        original(db, row, result)
        raise RuntimeError("Injected after message creation")

    acceptance.publish_content = broken
    acceptance.process(run["id"])
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, run["id"])
        binding = db.get(ConversationRun, run["id"])
        assert row.status == "succeeded" and row.result_text == "完整执行成果"
        assert binding.active and binding.handled_at is None
        assert binding.acceptance_error == "acceptance_unavailable"
        assert binding.acceptance_attempts == 1 and binding.next_acceptance_at is not None
        assert db.get(Message, run["id"]).body is None
    acceptance.publish_content = original
    acceptance.process(run["id"])
    acceptance.process(run["id"])
    with api_client.app.state.database.transaction() as db:
        assert db.get(Message, run["id"]).body == "完整执行成果"
        assert db.scalar(select(func.count()).select_from(Message)) == 2
        assert not db.get(ConversationRun, run["id"]).active
        assert db.get(Run, run["id"]).status == "succeeded"


def test_success_is_not_cancelled_while_business_acceptance_is_in_progress(api_client):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    acceptance = api_client.app.state.conversation_acceptance
    original = acceptance.publish_content
    entered, release = Event(), Event()
    api_client.app.state.runs.complete(Completion(run["id"], "已保存成果", "succeeded"))

    def pause(db, row, result):
        original(db, row, result)
        entered.set()
        assert release.wait(timeout=3)

    acceptance.publish_content = pause
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            finishing = pool.submit(acceptance.process, run["id"])
            assert entered.wait(timeout=3)
            cancelling = pool.submit(
                api_client.post, reply_path(api_client, run["id"]) + "/stop", json={}
            )
            release.set()
            finishing.result(timeout=5)
            assert cancelling.result(timeout=5).json()["response"]["status"] == "succeeded"
    finally:
        release.set()
        acceptance.publish_content = original
    assert read_reply(api_client, run["id"])["content"] == "已保存成果"


def test_missing_recovery_state_interrupts_attempt_without_hiding_history(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    store = api_client.app.state.run_worker.store
    first = submit(api_client, conversation).json()["response"]
    execute(api_client, monkeypatch, ScriptedModel(responses=[response("原有回答")]), first)
    pending = send(api_client, conversation, "尚未完成").json()["response"]
    assert store.claim(pending["id"])
    store.start_model(pending["id"], lambda db: None)
    store.checkpoint_saved(pending["id"], "missing-checkpoint")
    checkpoint_store(api_client).path.unlink(missing_ok=True)
    store.recover(True)
    asyncio.run(execute_run(api_client, pending["id"]))
    api_client.app.state.conversation_acceptance.sweep()
    done = read_reply(api_client, pending["id"])
    assert done["status"] == "interrupted"
    assert done["error"]["code"] == "checkpoint_unavailable"
    assert done["usage"]["total_tokens"] is None
    assert done["steps"][0]["status"] == "unknown"
    page = api_client.get(f"/api/conversations/{conversation['id']}/messages").json()["items"]
    assert page[1]["content"] == "原有回答" and page[1]["content_state"] == "complete"
    assert page[-1]["content_state"] != "complete"
    assert (
        api_client.get(f"/api/conversations/{conversation['id']}" + "/snapshot").json()[
            "conversation"
        ]["active_response_id"]
        is None
    )


def test_stable_results_and_product_messages_are_immutable(api_client):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    complete_run(api_client)(Completion(run_id=run["id"], content="正式回答", status="succeeded"))
    with api_client.app.state.database.transaction() as db:
        result = db.get(Message, run["id"])
        message = db.get(Message, run["reply_to_message_id"])
        with pytest.raises(ValueError, match="不可"):
            result.body = "覆盖历史"
        with pytest.raises(ValueError, match="不可"):
            message.body = "覆盖原输入"


def test_tool_actions_link_to_requesting_model_and_do_not_duplicate_public_messages(
    api_client, monkeypatch
):
    skill, _, _, conversation = setup(api_client)
    path = f"/skills/s-{skill['id']}/SKILL.md"
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {"name": "read_file", "id": "one", "args": {"file_path": path}},
                    {"name": "read_file", "id": "two", "args": {"file_path": path}},
                ],
            ),
            response("最终回答"),
        ]
    )
    run = submit(api_client, conversation).json()["response"]
    done = execute(api_client, monkeypatch, model, run)
    assert done["status"] == "succeeded"
    models = [item for item in done["steps"] if item["kind"] == "model_call"]
    tools = [item for item in done["steps"] if item["kind"] == "tool_call"]
    assert len(tools) == 2 and len(models) == 2
    assert {item["parent_action_id"] for item in tools} == {models[0]["id"]}
    with api_client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 2


def test_execution_does_not_import_product_or_http_implementations():
    root = Path(__file__).resolve().parents[1] / "app/execution"
    forbidden = ("app.conversations", "app.api", "fastapi")
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [item.name for item in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            assert not any(
                name == item or name.startswith(item + ".") for name in names for item in forbidden
            ), path


def test_finished_sdk_state_without_completion_marker_cannot_publish(api_client):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    with checkpoint_store(api_client).reader() as saver:
        state = publication_graph(saver).update_state(
            checkpoint_config("conversation:" + conversation["id"], run_id=run["id"]),
            {
                "messages": [
                    HumanMessage(id=run["reply_to_message_id"], content="请审阅文档"),
                    AIMessage(
                        id=f"run:{run['id']}:answer",
                        content="未经确认的输出",
                    ),
                ],
                "app_run_id": run["id"],
                "completed_run_id": "",
            },
            as_node="publish",
        )
    store.checkpoint_saved(run["id"], state["configurable"]["checkpoint_id"])
    asyncio.run(execute_run(api_client, run["id"]))
    done = read_reply(api_client, run["id"])
    assert done["status"] == "interrupted" and done["content"] == ""
    assert done["error"]["code"] == "runtime_interrupted"


def test_completion_notifies_after_commit_and_notification_failure_does_not_degrade(api_client):
    _, _, _, conversation = setup(api_client)
    reply = submit(api_client, conversation).json()["response"]
    worker = api_client.app.state.run_worker
    observed = []

    def notify():
        with api_client.app.state.database.transaction() as db:
            row = db.get(Run, reply["id"])
            observed.append((row.status, row.result_text))
        raise RuntimeError("hint lost")

    worker.set_completion_notifier(notify)
    asyncio.run(worker._complete(Completion(reply["id"], "已提交", "succeeded")))
    assert observed == [("succeeded", "已提交")]
    assert worker.status.accepting and not worker.pending_failures
    api_client.app.state.conversation_acceptance.sweep()
    assert read_reply(api_client, reply["id"])["content"] == "已提交"


def test_wake_during_scan_is_not_lost_and_does_not_bypass_persisted_backoff(
    api_client, monkeypatch
):
    _, _, _, conversation = setup(api_client)
    reply = submit(api_client, conversation).json()["response"]
    api_client.app.state.runs.complete(Completion(reply["id"], "完成", "succeeded"))
    acceptance = api_client.app.state.conversation_acceptance
    from datetime import timedelta

    from app.values import utc_now

    with api_client.app.state.database.transaction() as db:
        db.get(ConversationRun, reply["id"]).next_acceptance_at = utc_now() + timedelta(hours=1)
    processed = []
    monkeypatch.setattr(acceptance, "process", processed.append)
    acceptance.wake()
    acceptance.sweep()
    assert processed == []

    entered, release, again = Event(), Event(), Event()
    scans = []

    def scan():
        scans.append(True)
        if len(scans) == 1:
            entered.set()
            assert release.wait(5)
        else:
            again.set()

    monkeypatch.setattr(acceptance, "sweep", scan)
    acceptance.interval = 60

    async def scenario():
        await acceptance.start()
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            acceptance.wake()
            release.set()
            assert await asyncio.to_thread(again.wait, 5)
        finally:
            release.set()
            await acceptance.stop()

    asyncio.run(scenario())
