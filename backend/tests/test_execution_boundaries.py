"""Product publication, execution ownership and SDK failure boundaries."""

import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from checkpoint_helpers import publication_graph
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import func, select
from test_capability_runtime import ScriptedModel, execute, response, setup, submit
from test_conversations import send

from app.agent_runtime.checkpoints import CheckpointStore, checkpoint_config
from app.conversations.models import ConversationRun, Message
from app.execution.contracts import Completion
from app.execution.errors import PublicationFailure
from app.execution.models import Run


def test_product_history_and_next_context_do_not_read_sdk_state(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation, content="原问题").json()
    done = execute(api_client, monkeypatch, ScriptedModel(responses=[response("稳定回答")]), run)
    assert done["status"] == "succeeded" and done["result"]["content"] == "稳定回答"
    store = api_client.app.state.execution_store
    api_client.app.state.checkpoints.path.unlink()

    def forbidden(*args, **kwargs):
        raise AssertionError("Product reads must not open SDK storage")

    monkeypatch.setattr(CheckpointStore, "reader", forbidden)
    base = f"/api/conversations/{conversation['id']}"
    page = api_client.get(base + "/messages").json()["items"]
    assert [item["content"] for item in page] == ["原问题", "稳定回答"]
    assert all(item["published"] for item in page)
    assert (
        api_client.get(base + f"/questions/{run['input_message_id']}/preview").json()["answer"]
        == "稳定回答"
    )
    next_run = send(api_client, conversation, "追问").json()
    row, inputs = store.load(next_run["id"])
    assert [item["content"] for item in inputs] == ["原问题", "稳定回答", "追问"]
    assert row.checkpoint_id is None


def test_publication_failure_rolls_back_result_message_state_and_binding(api_client):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()
    store = api_client.app.state.execution_store
    publisher = api_client.app.state.conversation_commands.publisher
    original = publisher.publish_content
    assert store.claim(run["id"])

    def broken(db, row, result):
        original(db, row, result)
        raise RuntimeError("Injected after message creation")

    publisher.publish_content = broken
    try:
        with pytest.raises(PublicationFailure):
            api_client.app.state.conversation_commands.publisher(
                Completion(run_id=run["id"], content="候选回答", status="succeeded")
            )
        with api_client.app.state.database.transaction() as db:
            assert db.get(Run, run["id"]).status == "running"
            assert db.get(ConversationRun, run["id"]).active
            assert db.get(Message, run["output_message_id"]).body is None
            assert db.scalar(select(func.count()).select_from(Message)) == 2
    finally:
        publisher.publish_content = original
    api_client.app.state.conversation_commands.publisher(
        Completion(run_id=run["id"], content="正式回答", status="succeeded")
    )
    api_client.app.state.conversation_commands.publisher(
        Completion(run_id=run["id"], content="迟到的重复输出", status="succeeded")
    )
    with api_client.app.state.database.transaction() as db:
        assert db.get(Message, run["output_message_id"]).body == "正式回答"
        assert db.scalar(select(func.count()).select_from(Message)) == 2
        assert not db.get(ConversationRun, run["id"]).active
        assert db.get(Message, run["output_message_id"]).body == "正式回答"


def test_commit_wins_when_cancel_waits_for_the_same_business_writer(api_client):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()
    store = api_client.app.state.execution_store
    publisher = api_client.app.state.conversation_commands.publisher
    original = publisher.publish_content
    entered, release = Event(), Event()
    assert store.claim(run["id"])

    def pause(db, row, result):
        original(db, row, result)
        entered.set()
        assert release.wait(timeout=3)

    publisher.publish_content = pause
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            finishing = pool.submit(
                api_client.app.state.conversation_commands.publisher,
                Completion(run["id"], "已提交回答", "succeeded"),
            )
            assert entered.wait(timeout=3)
            cancelling = pool.submit(api_client.post, f"/api/runs/{run['id']}/cancel", json={})
            release.set()
            finishing.result(timeout=5)
            assert cancelling.result(timeout=5).json()["status"] == "succeeded"
    finally:
        release.set()
        publisher.publish_content = original
    assert api_client.get(f"/api/runs/{run['id']}").json()["result"]["content"] == "已提交回答"


def test_missing_recovery_state_interrupts_attempt_without_hiding_history(api_client):
    _, _, _, conversation = setup(api_client)
    store = api_client.app.state.execution_store
    first = submit(api_client, conversation).json()
    api_client.app.state.conversation_commands.publisher(
        Completion(run_id=first["id"], content="原有回答", status="succeeded")
    )
    pending = send(api_client, conversation, "尚未完成").json()
    assert store.claim(pending["id"])
    store.start_model(pending["id"], lambda db: None)
    store.checkpoint_saved(pending["id"], "missing-checkpoint")
    api_client.app.state.checkpoints.path.unlink(missing_ok=True)
    store.recover(True)
    asyncio.run(api_client.app.state.runner.coordinator.run(pending["id"]))
    done = api_client.get(f"/api/runs/{pending['id']}").json()
    assert done["status"] == "interrupted"
    assert done["error"]["code"] == "checkpoint_unavailable"
    assert done["usage"]["total_tokens"] is None
    assert done["actions"][0]["status"] == "unknown"
    page = api_client.get(f"/api/conversations/{conversation['id']}/messages").json()["items"]
    assert page[1]["content"] == "原有回答" and page[1]["published"]
    assert not page[-1]["published"]
    assert (
        api_client.get(f"/api/conversations/{conversation['id']}").json()["active_run_id"] is None
    )


def test_stable_results_and_product_messages_are_immutable(api_client):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()
    api_client.app.state.conversation_commands.publisher(
        Completion(run_id=run["id"], content="正式回答", status="succeeded")
    )
    with api_client.app.state.database.transaction() as db:
        result = db.get(Message, run["output_message_id"])
        message = db.get(Message, run["input_message_id"])
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
    run = submit(api_client, conversation).json()
    done = execute(api_client, monkeypatch, model, run)
    assert done["status"] == "succeeded"
    models = [item for item in done["actions"] if item["kind"] == "model_call"]
    tools = [item for item in done["actions"] if item["kind"] == "tool_call"]
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
    run = submit(api_client, conversation).json()
    store = api_client.app.state.execution_store
    with api_client.app.state.checkpoints.reader() as saver:
        state = publication_graph(saver).update_state(
            checkpoint_config(run["id"], run_id=run["id"]),
            {
                "messages": [
                    HumanMessage(id=run["input_message_id"], content="请审阅文档"),
                    AIMessage(id=f"run:{run['id']}:answer", content="未经确认的输出"),
                ],
                "app_run_id": run["id"],
                "completed_run_id": "",
            },
            as_node="publish",
        )
    store.checkpoint_saved(run["id"], state["configurable"]["checkpoint_id"])
    asyncio.run(api_client.app.state.runner.coordinator.run(run["id"]))
    done = api_client.get(f"/api/runs/{run['id']}").json()
    assert done["status"] == "interrupted" and done["result"] is None
    assert done["error"]["code"] == "runtime_interrupted"
