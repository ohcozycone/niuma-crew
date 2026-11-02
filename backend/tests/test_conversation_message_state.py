"""History, reconnection and SSE share the durable message/run/step projection."""

import asyncio
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import event
from test_conversations import send, setup_agent

from app.agent_runtime.streaming import ContentUpdate
from app.api.routes.conversations import events
from app.auth.permissions import ROLE_PERMISSIONS
from app.execution.contracts import Completion
from app.execution.models import RunAction
from app.infrastructure.database.fields import utc_now


def test_history_batches_all_steps_for_only_the_selected_message_page(api_client):
    _, _, conversation = setup_agent(api_client)
    store = api_client.app.state.runner.store
    first = send(api_client, conversation, "问题一").json()
    store.claim(first["id"])
    # 超过原步骤接口单页上限，history 仍必须包含完整步骤。
    with api_client.app.state.database.transaction() as db:
        db.add_all(
            RunAction(
                run_id=first["id"],
                sequence=i,
                action_key=f"model:{i}",
                kind="model_call",
                status="succeeded",
                safe_details={"round": i},
                output_text=f"过程{i}",
                started_at=utc_now(),
                finished_at=utc_now(),
            )
            for i in range(1, 103)
        )
    api_client.app.state.conversation_commands.publisher(
        Completion(run_id=first["id"], content="回答一", status="succeeded")
    )
    second = send(api_client, conversation, "问题二").json()
    store.claim(second["id"])
    store.start_action(second["id"], "model:1", "model_call")
    store.update_progress(
        second["id"], [ContentUpdate("model:1", "草稿二", "摘要二", False, False)]
    )
    path = f"/api/conversations/{conversation['id']}/messages"
    statements = []

    def record(_conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT") and "run_actions" in statement:
            statements.append(statement)

    engine = api_client.app.state.database.engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        page = api_client.get(path, params={"limit": 2}).json()
        assert len(statements) == 1
        statements.clear()
        full_page = api_client.get(path, params={"limit": 4}).json()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(statements) == 1
    assert len(full_page["items"][1]["run"]["actions"]) == 102
    assert page["items"][0]["run"] is None
    current = api_client.get(f"/api/runs/{second['id']}").json()
    assert page["items"][1]["run"] == current
    assert current["actions"][0]["output_text"] == "草稿二"
    assert current["actions"][0]["reasoning_text"] == "摘要二"
    assert all(step["run_id"] == second["id"] for step in current["actions"])
    older = api_client.get(path, params={"before_sequence": page["next_before_sequence"]}).json()
    saved = older["items"][-1]
    assert saved["content"] == "回答一" and saved["run"]["id"] == first["id"]
    assert len(saved["run"]["actions"]) == 102
    assert saved["run"]["actions"][-1]["output_text"] == "过程102"
    around = api_client.get(
        path, params={"around_message_id": first["input_message_id"], "limit": 2}
    ).json()
    assert around["items"][-1] == saved
    newer = api_client.get(path, params={"after_sequence": saved["sequence"]}).json()
    assert newer["items"][-1]["run"] == current


def test_sse_updates_body_and_steps_together_and_matches_final_history(api_client):
    _, _, conversation = setup_agent(api_client)
    run = send(api_client, conversation).json()
    store = api_client.app.state.runner.store
    store.claim(run["id"])
    store.start_action(run["id"], "model:1", "model_call")
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))

    async def disconnected():
        return False

    def payload(event_text):
        return api_client.execution(
            json.loads(
                next(line[6:] for line in event_text.splitlines() if line.startswith("data: "))
            )["response"]
        )

    async def observe():
        request = SimpleNamespace(app=api_client.app, is_disconnected=disconnected)
        stream = await events(
            UUID(conversation["id"]),
            UUID(run["output_message_id"]),
            request,
            actor,
            api_client.app.state.conversation_queries,
        )
        iterator = stream.body_iterator
        try:
            before = payload(await anext(iterator))
            assert before["actions"][0]["status"] == "running"
            store.update_progress(
                run["id"], [ContentUpdate("model:1", "新正文", "新摘要", False, False)]
            )
            middle = payload(await anext(iterator))
            assert middle["revision"] > before["revision"]
            assert (
                middle["current_model"]["output_text"]
                == middle["actions"][0]["output_text"]
                == "新正文"
            )
            assert middle["actions"][0]["reasoning_text"] == "新摘要"
            store.finish_action(run["id"], "model:1")
            api_client.app.state.conversation_commands.publisher(
                Completion(run_id=run["id"], content="最终回答", status="succeeded")
            )
            finished = await anext(iterator)
            assert "event: response.finished" in finished
            return payload(finished)
        finally:
            await iterator.aclose()

    final = asyncio.run(observe())
    assert final["assistant_content"] == "最终回答"
    assert final["actions"][0]["status"] == "succeeded"
    history = api_client.get(f"/api/conversations/{conversation['id']}/messages").json()["items"]
    assert history[-1]["content"] == "最终回答" and history[-1]["run"] == final
    assert api_client.app.state.subscriptions == {}
    assert "test-only-secret" not in json.dumps(history) and "config_snapshot" not in json.dumps(
        history
    )


def test_retry_keeps_steps_on_the_original_assistant_message(api_client, monkeypatch):
    _, _, conversation = setup_agent(api_client)
    first = send(api_client, conversation).json()
    store = api_client.app.state.runner.store
    store.claim(first["id"])
    store.start_action(first["id"], "model:1", "model_call")
    api_client.app.state.conversation_commands.publisher(
        Completion(run_id=first["id"], content="", status="failed", error="upstream_unavailable")
    )
    second = api_client.post(
        f"/api/runs/{first['id']}/retry", json={"client_request_id": str(uuid4())}
    ).json()
    store.claim(second["id"])
    store.start_action(second["id"], "model:1", "model_call")
    path = f"/api/conversations/{conversation['id']}/messages"
    history = api_client.get(path).json()["items"]
    assert [message["role"] for message in history] == ["user", "assistant", "assistant"]
    assert history[1]["run"]["actions"][0]["run_id"] == first["id"]
    assert history[2]["run"]["actions"][0]["run_id"] == second["id"]
    assert history[1]["run"]["actions"][0]["status"] == "unknown"
    assert history[2]["run"]["actions"][0]["status"] == "running"
    monkeypatch.setitem(ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] - {"runs:read"})
    assert api_client.get(path).status_code == 403
