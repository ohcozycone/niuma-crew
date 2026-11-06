"""History, reconnection and SSE share the durable message/run/step projection."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from run_helpers import complete_run, latest_model, read_reply, reply_path
from sqlalchemy import event
from starlette.responses import Response
from test_conversations import send, setup_agent

from app.api.routes.conversations import events
from app.api.streaming import subscribe
from app.auth.permissions import ROLE_PERMISSIONS
from app.execution.contracts import Completion
from app.execution.models import RunAction
from app.execution.runtime.streaming import ContentUpdate
from app.values import utc_now


def test_history_batches_all_steps_for_only_the_selected_message_page(api_client, monkeypatch):
    from test_capability_runtime import ScriptedModel, execute, response

    _, _, conversation = setup_agent(api_client)
    store = api_client.app.state.run_worker.store
    first = send(api_client, conversation, "问题一").json()["response"]
    assert (
        execute(api_client, monkeypatch, ScriptedModel(responses=[response("回答一")]), first)[
            "status"
        ]
        == "succeeded"
    )
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
            for i in range(2, 103)
        )
    second = send(api_client, conversation, "问题二").json()["response"]
    store.claim(second["id"])
    store.start_action(second["id"], "model:1", "model_call")
    store.update_progress(
        second["id"],
        [ContentUpdate("model:1", "草稿二", "摘要二", False, False)],
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
    assert len(full_page["items"][1]["steps"]) == 102
    assert page["items"][0]["role"] == "user"
    current = read_reply(api_client, second["id"])
    assert page["items"][1] == current
    assert current["steps"][0]["output_text"] == "草稿二"
    assert current["steps"][0]["reasoning_text"] == "摘要二"
    assert all(step["run_id"] == second["id"] for step in current["steps"])
    older = api_client.get(path, params={"before_sequence": page["next_before_sequence"]}).json()
    saved = older["items"][-1]
    assert saved["content"] == "回答一" and saved["id"] == first["id"]
    assert len(saved["steps"]) == 102
    assert saved["steps"][-1]["output_text"] == "过程102"
    around = api_client.get(
        path, params={"around_message_id": first["reply_to_message_id"], "limit": 2}
    ).json()
    assert around["items"][-1] == saved
    newer = api_client.get(path, params={"after_sequence": saved["sequence"]}).json()
    assert newer["items"][-1] == current


def test_sse_updates_body_and_steps_together_and_matches_final_history(api_client):
    _, _, conversation = setup_agent(api_client)
    run = send(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    store.claim(run["id"])
    store.start_action(run["id"], "model:1", "model_call")
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))

    def payload(event):
        return event.data.model_dump(mode="json")["response"]

    async def observe():
        request = SimpleNamespace(app=api_client.app)
        dependency = subscribe(
            conversation["id"],
            run["id"],
            request,
            Response(),
            actor,
            api_client.app.state.conversation_queries,
        )
        subscription = await anext(dependency)
        iterator = events(subscription)
        try:
            before = payload(await anext(iterator))
            assert before["steps"][0]["status"] == "running"
            store.update_progress(
                run["id"],
                [ContentUpdate("model:1", "新正文", "新摘要", False, False)],
            )
            middle = payload(await anext(iterator))
            assert middle["version"] > before["version"]
            assert (
                latest_model(middle)["output_text"] == middle["steps"][0]["output_text"] == "新正文"
            )
            assert middle["steps"][0]["reasoning_text"] == "新摘要"
            store.finish_action(run["id"], "model:1")
            complete_run(api_client)(
                Completion(
                    run_id=run["id"],
                    content="最终回答",
                    status="succeeded",
                )
            )
            finished = await anext(iterator)
            assert finished.event == "response.finished"
            return payload(finished)
        finally:
            await iterator.aclose()
            await dependency.aclose()

    final = asyncio.run(observe())
    assert final["content"] == "最终回答"
    assert final["steps"][0]["status"] == "succeeded"
    history = api_client.get(f"/api/conversations/{conversation['id']}/messages").json()["items"]
    assert history[-1]["content"] == "最终回答" and history[-1] == final
    assert api_client.app.state.subscriptions == {}
    assert "test-only-secret" not in json.dumps(history) and "config_snapshot" not in json.dumps(
        history
    )


def test_retry_keeps_steps_on_the_original_assistant_message(api_client, monkeypatch):
    _, _, conversation = setup_agent(api_client)
    first = send(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    store.claim(first["id"])
    store.start_action(first["id"], "model:1", "model_call")
    complete_run(api_client)(
        Completion(
            run_id=first["id"],
            content="",
            status="failed",
            error="upstream_unavailable",
        )
    )
    second = api_client.post(
        reply_path(api_client, first["id"]) + "/retry", json={"client_request_id": str(uuid4())}
    ).json()["response"]
    store.claim(second["id"])
    store.start_action(second["id"], "model:1", "model_call")
    path = f"/api/conversations/{conversation['id']}/messages"
    history = api_client.get(path).json()["items"]
    assert [message["role"] for message in history] == ["user", "assistant", "assistant"]
    assert history[1]["steps"][0]["run_id"] == first["id"]
    assert history[2]["steps"][0]["run_id"] == second["id"]
    assert history[1]["steps"][0]["status"] == "unknown"
    assert history[2]["steps"][0]["status"] == "running"
    monkeypatch.setitem(ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] - {"runs:read"})
    assert api_client.get(path).status_code == 403
