"""Real persistence/HTTP semantics with controlled model streams; no external API calls."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from configuration_helpers import patch_current, set_submission_limits
from fastapi.testclient import TestClient
from run_helpers import (
    complete_run,
    empty_conversation,
    execute_run,
    latest_model,
    read_reply,
    reply_path,
)
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.auth.models import AuthSession
from app.auth.permissions import ROLE_PERMISSIONS
from app.bootstrap import create_app
from app.execution.contracts import (
    AgentOutput,
    AgentRequest,
    Completion,
    ContentUpdate,
)
from app.execution.errors import ExecutionFailure
from app.execution.models import Run
from app.execution.prompts import compose_system_prompt
from app.infrastructure.database.transactions import reserve_writer
from app.values import utc_now


def set_executor(client, execute):
    client.app.state.run_worker.task_factory.keywords["agent"] = execute


async def draft(hooks, text):
    if "model:1" not in hooks.progress.contents:
        await hooks.start("model:1", "model_call", {"round": 1})
    await hooks.report_content(ContentUpdate("model:1", text, "", False, False))


def setup_agent(client):
    connection_response = client.post(
        "/api/model-connections", json={"name": str(uuid4()), "api_key": "test-only-secret"}
    )
    assert connection_response.status_code == 201, connection_response.text
    connection = connection_response.json()
    agent_response = client.post(
        "/api/agents",
        json={
            "name": f"对话员工-{uuid4()}",
            "avatar_id": "admin",
            "system_prompt": "仅使用中文回答。",
            "model_connection_id": connection["id"],
        },
    )
    assert agent_response.status_code == 201, agent_response.text
    agent = agent_response.json()
    conversation = empty_conversation(client, agent["id"])
    return connection, agent, conversation


def send(client, conversation, content="你好", key=None):
    return client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"client_request_id": key or str(uuid4()), "content": content},
    )


def wait_run(
    client,
    id,
    predicate=lambda r: (
        r["status"] not in ("queued", "running", "cancelling") and r.get("acceptance") != "pending"
    ),
):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        result = client.get(reply_path(client, id))
        assert result.status_code == 200, result.text
        row = result.json()["response"]
        if predicate(row):
            return row
        time.sleep(0.02)
    pytest.fail(f"run did not reach expected state: {row}")


@pytest.fixture
def live_client(api_client, migrated_config):
    settings = replace(
        migrated_config,
        runtime=replace(
            migrated_config.runtime,
            enabled=True,
            poll_interval=0.01,
            flush_interval=0.01,
            auth_interval=0.03,
        ),
    )
    with TestClient(
        create_app(settings),
        headers={"Origin": "http://localhost:3000", "Content-Type": "application/json"},
    ) as client:
        client.cookies.update(api_client.cookies)
        yield client


def test_idempotency_ordering_cancel_retry_and_delete_protection(api_client):
    connection, agent, conversation = setup_agent(api_client)
    key = str(uuid4())
    first = send(api_client, conversation, key=key)
    assert first.status_code == 202
    row = first.json()["response"]
    assert send(api_client, conversation, key=key).json()["response"]["id"] == row["id"]
    assert send(api_client, conversation, key=key).status_code == 200
    assert send(api_client, conversation, "different", key).status_code == 409
    assert send(api_client, conversation).json()["detail"]["code"] == "conversation_busy"
    assert (
        api_client.delete(f"/api/agents/{agent['id']}").json()["detail"]["code"]
        == "agent_has_conversations"
    )
    patch_current(api_client, f"/api/agents/{agent['id']}", json={"model_connection_id": None})
    assert api_client.delete(f"/api/model-connections/{connection['id']}").status_code == 409
    cancelled = api_client.post(reply_path(api_client, row["id"]) + "/stop", json={}).json()[
        "response"
    ]
    assert cancelled["status"] == "cancelled"
    assert (
        api_client.post(reply_path(api_client, row["id"]) + "/stop", json={}).json()["response"][
            "version"
        ]
        == cancelled["version"]
    )
    patch_current(
        api_client,
        f"/api/agents/{agent['id']}",
        json={"model_connection_id": connection["id"]},
    )
    retry_key = str(uuid4())
    retry = api_client.post(
        reply_path(api_client, row["id"]) + "/retry", json={"client_request_id": retry_key}
    )
    assert retry.status_code == 202
    second = retry.json()["response"]
    assert second["id"] != row["id"] and second["reply_to_message_id"] == row["reply_to_message_id"]
    assert (
        api_client.post(
            reply_path(api_client, row["id"]) + "/retry", json={"client_request_id": retry_key}
        ).json()["response"]["id"]
        == second["id"]
    )
    page = api_client.get(f"/api/conversations/{conversation['id']}/messages?limit=2").json()
    assert [m["sequence"] for m in page["items"]] == [2, 3] and page["next_before_sequence"] == 2
    previous = api_client.get(
        f"/api/conversations/{conversation['id']}/messages?before_sequence=2"
    ).json()
    assert [m["role"] for m in previous["items"]] == ["user"]
    assert "test-only-secret" not in json.dumps(page)
    assert api_client.get("/api/conversations").json()["total"] == 1


def test_concurrent_requests_reserve_one_run_and_enforce_database_fk(api_client):
    _, _, conversation = setup_agent(api_client)
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: send(api_client, conversation, key=key), range(4)))
    assert sorted(r.status_code for r in results) == [200, 200, 200, 202]
    assert len({r.json()["response"]["id"] for r in results}) == 1
    _, _, other = setup_agent(api_client)
    different = send(api_client, other).json()["response"]
    db = api_client.app.state.database
    with pytest.raises(IntegrityError):
        with db.transaction() as session:
            session.execute(
                update(Run)
                .where(Run.id == different["id"])
                .values(retry_of_run_id=results[0].json()["response"]["id"])
            )


def test_checkpoint_history_paginates_many_retries_without_missing_answers(api_client):
    _, _, conversation = setup_agent(api_client)
    run = send(api_client, conversation, "原问题").json()["response"]
    for attempt in range(9):
        complete_run(api_client)(
            Completion(
                run_id=run["id"],
                content=f"失败回答{attempt}",
                status="failed",
                error="output_limit_exceeded",
            )
        )
        if attempt < 8:
            retry = api_client.post(
                reply_path(api_client, run["id"]) + "/retry",
                json={"client_request_id": str(uuid4())},
            )
            assert retry.status_code == 202, retry.text
            run = retry.json()["response"]
    later = send(api_client, conversation, "后续问题").json()["response"]
    complete_run(api_client)(Completion(run_id=later["id"], content="后续回答", status="succeeded"))
    items, before = [], None
    while True:
        params = {"limit": 2}
        if before is not None:
            params["before_sequence"] = before
        page = api_client.get(
            f"/api/conversations/{conversation['id']}/messages",
            params=params,
        ).json()
        items = page["items"] + items
        if not page["has_more"]:
            break
        assert before is None or page["next_before_sequence"] < before
        before = page["next_before_sequence"]
    assert [m["sequence"] for m in items] == list(range(1, 13))
    assert [m["content"] for m in items] == [
        "原问题",
        *[f"失败回答{attempt}" for attempt in range(9)],
        "后续问题",
        "后续回答",
    ]


def test_permissions_validation_and_resource_scope(api_client, migrated_config, monkeypatch):
    _, _, conversation = setup_agent(api_client)
    row = send(api_client, conversation).json()["response"]
    with TestClient(
        create_app(migrated_config),
        headers={"Origin": "http://localhost:3000", "Content-Type": "application/json"},
    ) as guest:
        assert guest.get("/api/conversations").status_code == 401
        guest.post("/api/auth/guest", json={})
        for path in (
            "/api/conversations",
            f"/api/conversations/{conversation['id']}/snapshot",
            f"/api/conversations/{conversation['id']}/messages",
            f"/api/conversations/{conversation['id']}/questions",
            f"/api/conversations/{conversation['id']}/questions/{row['reply_to_message_id']}/preview",
            reply_path(api_client, row["id"]),
            reply_path(api_client, row["id"]) + "/events",
        ):
            assert guest.get(path).status_code == 403
        assert guest.post(reply_path(guest, row["id"]) + "/stop", json={}).status_code == 403
    monkeypatch.setitem(ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] - {"runs:create"})
    assert send(api_client, conversation).status_code == 403
    monkeypatch.setitem(ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] | {"runs:create"})
    api_client.post(reply_path(api_client, row["id"]) + "/stop", json={})
    assert send(api_client, conversation, " ").status_code == 422
    assert send(api_client, conversation, "字" * 6000).status_code == 422
    assert (
        api_client.post(
            f"/api/conversations/{conversation['id']}/messages",
            json={"client_request_id": str(uuid4()), "content": "x", "api_key": "do-not-echo"},
        ).status_code
        == 422
    )


def test_real_runner_stream_persists_without_fabricating_sdk_memory(live_client):
    calls = []

    async def execute(input, hooks):
        calls.append((input.snapshot, input.messages))
        assert input.config.api_key.get_secret_value() == "test-only-secret"
        await draft(hooks, "你好")
        await asyncio.sleep(0.2)
        await hooks.finish(
            "model:1", content=ContentUpdate("model:1", "你好，已收到。", "", False, False)
        )
        return AgentOutput(
            "你好，已收到。", {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        )

    set_executor(live_client, execute)
    _, agent, conversation = setup_agent(live_client)
    first = send(live_client, conversation).json()["response"]
    partial = wait_run(
        live_client,
        first["id"],
        lambda r: bool((latest_model(r) or {}).get("output_text")) if latest_model(r) else False,
    )
    assert partial["content"] == "你好" and latest_model(partial)["output_text"] == "你好"
    assert partial["status"] == "running"
    patch_current(live_client, f"/api/agents/{agent['id']}", json={"system_prompt": "新的工作指令"})
    completed = wait_run(live_client, first["id"])
    assert completed["status"] == "succeeded" and completed["usage"]["total_tokens"] == 15
    events = live_client.get(reply_path(live_client, first["id"]) + "/events")
    assert "event: response.finished" in events.text and "你好" in events.text
    assert live_client.app.state.subscriptions == {}
    assert "test-only-secret" not in events.text and "system_prompt" not in events.text
    unavailable = send(live_client, conversation, "继续")
    assert unavailable.status_code == 409
    assert unavailable.json()["detail"]["code"] == "checkpoint_unavailable"
    independent = empty_conversation(live_client, agent["id"])
    second = send(live_client, independent, "继续").json()["response"]
    assert wait_run(live_client, second["id"])["status"] == "succeeded"
    assert calls[0][0]["system_prompt"] == compose_system_prompt(
        "", "仅使用中文回答。", agent_name=agent["name"]
    )
    assert calls[1][0]["system_prompt"] == compose_system_prompt(
        "", "新的工作指令", agent_name=agent["name"]
    )
    assert [(item["role"], item["content"]) for item in calls[1][1]] == [("user", "继续")]
    assert (
        live_client.get(f"/api/conversations/{conversation['id']}" + "/snapshot").json()[
            "conversation"
        ]["active_response_id"]
        is None
    )
    assert live_client.delete(f"/api/agents/{agent['id']}").status_code == 409


@pytest.mark.parametrize(
    "mode,code",
    [
        ("failure", "upstream_rate_limited"),
        ("length", "output_limit_exceeded"),
        ("empty", "empty_response"),
        ("broken", "upstream_stream_error"),
        ("timeout", "run_timeout"),
    ],
)
def test_failures_preserve_partial_and_sanitize(live_client, mode, code):
    async def execute(input, hooks):
        if mode == "timeout":
            raise TimeoutError("test-only-secret")
        if mode == "empty":
            return AgentOutput("")
        await draft(hooks, "部分")
        raise ExecutionFailure(code, "部分" if mode == "length" else None)

    set_executor(live_client, execute)
    _, _, conversation = setup_agent(live_client)
    result = wait_run(live_client, send(live_client, conversation).json()["response"]["id"])
    assert result["status"] == "failed" and result["error"]["code"] == code
    assert "test-only-secret" not in json.dumps(result)
    assert result["content"] == ("部分" if mode == "length" else "")
    assert ("已保留未完成的输出" in result["error"]["message"]) == (mode == "length")


def test_stop_closes_upstream_and_retry_excludes_failed_context(live_client):
    closed, calls = [], []

    async def execute(input, hooks):
        calls.append(input.messages)
        try:
            await draft(hooks, "部分输出")
            await asyncio.sleep(30)
        finally:
            closed.append(True)

    set_executor(live_client, execute)
    _, _, conversation = setup_agent(live_client)
    row = send(live_client, conversation).json()["response"]
    wait_run(live_client, row["id"], lambda r: bool(latest_model(r)))
    assert (
        live_client.post(reply_path(live_client, row["id"]) + "/stop", json={}).json()["response"][
            "status"
        ]
        == "cancelling"
    )
    result = wait_run(live_client, row["id"])
    assert result["status"] == "cancelled" and result["content"] == "" and closed
    steps = read_reply(live_client, row["id"])["steps"]
    assert steps[0]["output_text"] == "部分输出" and steps[0]["status"] == "unknown"

    async def success(input, hooks):
        calls.append(input.messages)
        return AgentOutput("重试成功")

    set_executor(live_client, success)
    retried = live_client.post(
        reply_path(live_client, row["id"]) + "/retry", json={"client_request_id": str(uuid4())}
    ).json()["response"]
    assert wait_run(live_client, retried["id"])["status"] == "succeeded"
    assert [(item["role"], item["content"]) for item in calls[-1]] == [("user", "你好")]
    assert (
        live_client.post(
            reply_path(live_client, row["id"]) + "/retry", json={"client_request_id": str(uuid4())}
        ).status_code
        == 409
    )


def test_session_revocation_stops_execution_without_touching_activity(live_client):
    async def execute(input, hooks):
        await draft(hooks, "已开始")
        await asyncio.sleep(30)

    set_executor(live_client, execute)
    _, _, conversation = setup_agent(live_client)
    row = send(live_client, conversation).json()["response"]
    wait_run(live_client, row["id"], lambda r: r["status"] == "running")
    db = live_client.app.state.database
    with db.transaction() as session:
        # Reserve the writer before reading while the background runner is saving progress.
        reserve_writer(session, AuthSession.__table__)
        run = session.get(Run, row["id"])
        login = session.get(AuthSession, run.initiated_by_session_id)
        previous = login.last_seen_at
        login.revoked_at = utc_now()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with db.transaction() as session:
            run = session.get(Run, row["id"])
            if run.status == "cancelled":
                assert run.error_code == "actor_session_invalid"
                assert (
                    session.get(AuthSession, run.initiated_by_session_id).last_seen_at == previous
                )
                return
        time.sleep(0.02)
    pytest.fail("revoked run not cancelled")


def test_startup_recovery_and_single_process_lock(api_client, migrated_config, monkeypatch):
    from test_capability_runtime import ScriptedModel, response

    monkeypatch.setattr(
        "app.llm.factory.create_chat_model",
        lambda *a, **k: ScriptedModel(responses=[response("恢复完成")]),
    )
    _, _, conversation = setup_agent(api_client)
    row = send(api_client, conversation).json()["response"]
    settings = replace(migrated_config, runtime=replace(migrated_config.runtime, enabled=True))
    assert not settings.runner_lock_file.parent.exists()
    with TestClient(create_app(settings)) as client:
        assert settings.runner_lock_file.stat().st_mode & 0o777 == 0o600
        client.cookies.update(api_client.cookies)
        assert wait_run(client, row["id"])["status"] == "succeeded"

        async def waiting(input, hooks):
            await asyncio.sleep(30)

        set_executor(client, waiting)
        new = send(api_client, conversation).json()["response"]
        with pytest.raises(RuntimeError, match="一个后端进程"):
            with TestClient(create_app(settings)):
                pass
        assert read_reply(client, new["id"])["status"] != "interrupted"
        # Avoid making an external request in this lock-only test.
        api_client.post(reply_path(api_client, new["id"]) + "/stop", json={})
    # Reopening the same lock after shutdown must succeed.
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200


def test_configuration_version_and_queue_timeout(api_client):
    connection, _, conversation = setup_agent(api_client)
    row = send(api_client, conversation).json()["response"]
    runner = api_client.app.state.run_worker
    patch_current(
        api_client, f"/api/model-connections/{connection['id']}", json={"model_id": "changed"}
    )
    asyncio.run(execute_run(api_client, row["id"]))
    api_client.app.state.conversation_acceptance.sweep()
    result = read_reply(api_client, row["id"])
    assert result["error"]["code"] == "model_configuration_changed"
    retry = api_client.post(
        reply_path(api_client, row["id"]) + "/retry", json={"client_request_id": str(uuid4())}
    ).json()["response"]
    with api_client.app.state.database.transaction() as db:
        db.get(Run, retry["id"]).created_at = utc_now() - timedelta(seconds=60)

    async def one_tick():
        task = asyncio.create_task(runner._loop())
        await asyncio.sleep(0.1)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(one_tick())
    api_client.app.state.conversation_acceptance.sweep()
    assert read_reply(api_client, retry["id"])["error"]["code"] == "queue_timeout"


def test_terminal_and_cancellation_races_never_resurrect(api_client):
    _, _, conversation = setup_agent(api_client)
    row = send(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    store.claim(row["id"])
    api_client.post(reply_path(api_client, row["id"]) + "/stop", json={})
    complete_run(api_client)(Completion(run_id=row["id"], content="迟到的完成", status="succeeded"))
    result = read_reply(api_client, row["id"])
    assert result["status"] == "cancelled"
    complete_run(api_client)(Completion(run_id=row["id"], content="不可覆盖", status="succeeded"))
    assert read_reply(api_client, row["id"]) == result


def test_capacity_input_and_configuration_limits(api_client, monkeypatch):
    from test_capability_runtime import ScriptedModel, execute, response

    _, agent, first = setup_agent(api_client)
    _, _, second = setup_agent(api_client)
    _, _, third = setup_agent(api_client)
    a, b = send(api_client, first).json()["response"], send(api_client, second).json()["response"]
    assert send(api_client, third).status_code == 429
    store = api_client.app.state.run_worker.store
    assert (
        execute(api_client, monkeypatch, ScriptedModel(responses=[response("回答一")]), a)["status"]
        == "succeeded"
    )
    assert (
        execute(api_client, monkeypatch, ScriptedModel(responses=[response("另一个对话")]), b)[
            "status"
        ]
        == "succeeded"
    )
    next_run = send(api_client, first, "第二问").json()["response"]
    assert (
        execute(api_client, monkeypatch, ScriptedModel(responses=[response("回答二")]), next_run)[
            "status"
        ]
        == "succeeded"
    )
    final = send(api_client, first, "第三问").json()["response"]
    row, messages = store.load(final["id"])
    assert [(item["role"], item["content"]) for item in messages] == [
        ("user", "第三问"),
    ]
    assert "test-only-secret" not in json.dumps(row.config_snapshot)
    api_client.post(reply_path(api_client, final["id"]) + "/stop", json={})
    patch_current(api_client, f"/api/agents/{agent['id']}", json={"is_active": False})
    assert send(api_client, first).json()["detail"]["code"] == "agent_inactive"
    patch_current(
        api_client,
        f"/api/agents/{agent['id']}",
        json={"is_active": True, "model_connection_id": None},
    )
    assert send(api_client, first).json()["detail"]["code"] == "model_not_configured"


def test_output_limit_and_persistence_failure_stop_generation(live_client, monkeypatch):
    _, _, conversation = setup_agent(live_client)
    set_submission_limits(live_client.app.state.conversation_commands, max_output_bytes=6)

    async def oversized(input, hooks):
        return AgentOutput("一二三四五六")

    set_executor(live_client, oversized)
    result = wait_run(live_client, send(live_client, conversation).json()["response"]["id"])
    assert result["error"]["code"] == "output_limit_exceeded" and result["content"] == "一二"
    closed = []

    async def slow(input, hooks):
        try:
            await draft(hooks, "a")
            await asyncio.sleep(30)
        finally:
            closed.append(True)

    runner = live_client.app.state.run_worker
    set_executor(live_client, slow)
    original, failed = runner.store.update_progress, []

    def persist(*args):
        if not failed:
            failed.append(True)
            from sqlalchemy.exc import OperationalError

            raise OperationalError("hidden", {}, Exception("disk unavailable"))
        return original(*args)

    monkeypatch.setattr(runner.store, "update_progress", persist)
    result = wait_run(live_client, send(live_client, conversation).json()["response"]["id"])
    assert closed and result["error"]["code"] == "persistence_unavailable"


def test_owner_scope_is_independent_of_role_mapping(api_client):
    from dataclasses import replace

    from app.errors import NotFoundError

    _, _, conversation = setup_agent(api_client)
    auth = api_client.app.state.auth
    actor = auth.resolve(api_client.cookies.get("app_session"))
    limited = replace(actor, user_id=str(uuid4()), role="future-member")
    ROLE_PERMISSIONS["future-member"] = {"conversations:read"}
    try:
        service = api_client.app.state.conversation_queries
        assert service.list(limited).total == 0
        with pytest.raises(NotFoundError):
            service.snapshot(limited, conversation["id"])
        with pytest.raises(NotFoundError):
            service.questions(limited, conversation["id"], start_number=50)
        with pytest.raises(NotFoundError):
            service.messages(limited, conversation["id"], around=str(uuid4()))
    finally:
        ROLE_PERMISSIONS.pop("future-member")


def test_question_outline_and_direct_windows_are_bidirectional(api_client, monkeypatch):
    from test_capability_runtime import ScriptedModel, execute, response

    _, _, conversation = setup_agent(api_client)
    runs = []
    for number in range(1, 51):
        run = send(api_client, conversation, f"问题 {number}：历史定位").json()["response"]
        assert (
            execute(
                api_client, monkeypatch, ScriptedModel(responses=[response(f"回答 {number}")]), run
            )["status"]
            == "succeeded"
        )
        runs.append(run)
    base = f"/api/conversations/{conversation['id']}"
    outline = api_client.get(base + "/questions?limit=20").json()
    assert outline["total"] == 50
    assert [q["number"] for q in outline["items"]] == list(range(1, 21))
    rest = api_client.get(
        base + f"/questions?after_sequence={outline['next_after_sequence']}"
    ).json()
    assert [q["number"] for q in rest["items"]] == list(range(21, 51))
    found = api_client.get(base + "/questions", params={"q": "问题 50"}).json()
    assert [q["number"] for q in found["items"]] == [50]
    assert found["items"][0]["id"] == runs[-1]["reply_to_message_id"]
    anchored = api_client.get(
        base + "/questions",
        params={"limit": 1, "anchor_message_id": runs[-1]["reply_to_message_id"]},
    ).json()
    assert len(anchored["items"]) == 1 and anchored["items"][0]["number"] == 1
    assert anchored["anchor"]["number"] == 50
    filtered_anchor = api_client.get(
        base + "/questions",
        params={"q": "不存在的问题", "anchor_message_id": runs[-1]["reply_to_message_id"]},
    ).json()
    assert (
        filtered_anchor["items"] == []
        and filtered_anchor["anchor"]["id"] == runs[-1]["reply_to_message_id"]
    )
    assert (
        api_client.get(base + "/questions", params={"anchor_message_id": runs[-1]["id"]}).json()[
            "anchor"
        ]
        is None
    )
    assert api_client.get(base + "/questions?q=%25").json()["total"] == 0
    numbered = api_client.get(base + "/questions", params={"start_number": 21, "limit": 5}).json()
    assert numbered["total"] == 50
    assert [q["number"] for q in numbered["items"]] == list(range(21, 26))
    assert numbered["items"][0]["id"] == runs[20]["reply_to_message_id"]
    assert numbered["next_after_sequence"] == numbered["items"][-1]["sequence"]
    tail = api_client.get(base + "/questions?start_number=48&limit=10").json()
    assert [q["number"] for q in tail["items"]] == [48, 49, 50]
    assert tail["next_after_sequence"] is None
    beyond = api_client.get(base + "/questions?start_number=51").json()
    assert beyond["items"] == [] and beyond["total"] == 50
    assert api_client.get(base + "/questions?start_number=0").status_code == 422
    assert (
        api_client.get(base + "/questions?start_number=2&after_sequence=3").json()["detail"]["code"]
        == "question_cursor_conflict"
    )
    first = api_client.get(
        base + "/messages",
        params={
            "around_message_id": runs[0]["reply_to_message_id"],
            "limit": 6,
        },
    ).json()
    assert [m["sequence"] for m in first["items"]] == list(range(1, 7))
    assert first["next_before_sequence"] is None and first["next_after_sequence"] == 6
    next_page = api_client.get(base + "/messages?after_sequence=6&limit=6").json()
    assert [m["sequence"] for m in next_page["items"]] == list(range(7, 13))
    assert next_page["next_before_sequence"] == 7 and next_page["next_after_sequence"] == 12
    middle = api_client.get(
        base + "/messages",
        params={
            "around_message_id": runs[24]["reply_to_message_id"],
            "limit": 6,
        },
    ).json()
    assert [m["sequence"] for m in middle["items"]] == list(range(47, 53))
    previous = api_client.get(base + "/messages?before_sequence=47&limit=6").json()
    assert [m["sequence"] for m in previous["items"]] == list(range(41, 47))
    latest = api_client.get(
        base + "/messages",
        params={
            "around_message_id": runs[-1]["reply_to_message_id"],
        },
    ).json()
    assert latest["items"][-1]["content"] == "回答 50"
    assert latest["next_after_sequence"] is None
    assert (
        api_client.get(
            base + "/messages",
            params={
                "around_message_id": "999999999999",
            },
        ).status_code
        == 404
    )
    assert api_client.get(base + "/messages?before_sequence=10&after_sequence=3").status_code == 422
    assert api_client.get(base + "/messages?after_sequence=0").status_code == 422


def test_retry_is_one_question_with_all_outputs_in_both_directions(api_client, monkeypatch):
    from test_capability_runtime import ScriptedModel, execute, response

    _, _, conversation = setup_agent(api_client)
    first = send(api_client, conversation, "同一个问题").json()["response"]
    complete_run(api_client)(
        Completion(
            run_id=first["id"],
            content="初次失败",
            status="failed",
            error="upstream_unavailable",
        )
    )
    retry = api_client.post(
        reply_path(api_client, first["id"]) + "/retry", json={"client_request_id": str(uuid4())}
    ).json()["response"]
    assert (
        execute(api_client, monkeypatch, ScriptedModel(responses=[response("重试成功")]), retry)[
            "status"
        ]
        == "succeeded"
    )
    base = f"/api/conversations/{conversation['id']}"
    outline = api_client.get(base + "/questions").json()
    assert outline["total"] == 1 and outline["items"][0]["number"] == 1
    page = api_client.get(base + "/messages?after_sequence=1&limit=1").json()
    assert [m["content"] for m in page["items"]] == ["初次失败"]
    assert page["next_after_sequence"] == 2
    page = api_client.get(base + "/messages?after_sequence=2").json()
    assert [m["content"] for m in page["items"]] == ["重试成功"]
    assert page["next_after_sequence"] is None

    second = send(api_client, conversation, "重试后的第二个问题").json()["response"]
    complete_run(api_client)(
        Completion(run_id=second["id"], content="第二次回答", status="succeeded")
    )
    numbered = api_client.get(base + "/questions?start_number=2").json()
    assert numbered["total"] == 2
    assert [(q["number"], q["id"]) for q in numbered["items"]] == [
        (2, second["reply_to_message_id"])
    ]
    assert numbered["items"][0]["sequence"] > 3


def test_question_preview_reads_the_latest_attempt_without_a_message_window(
    api_client, monkeypatch
):
    from app.conversations import queries as projections

    _, _, conversation = setup_agent(api_client)
    run = send(api_client, conversation, "# 固定问题\n**用户原文**").json()["response"]
    question_id = run["reply_to_message_id"]
    for _ in range(9):
        complete_run(api_client)(
            Completion(
                run_id=run["id"],
                content="旧的失败回答",
                status="failed",
                error="upstream_unavailable",
            )
        )
        run = api_client.post(
            reply_path(api_client, run["id"]) + "/retry", json={"client_request_id": str(uuid4())}
        ).json()["response"]
    complete_run(api_client)(
        Completion(
            run_id=run["id"],
            content="**最新回答**\n" + "甲" * 600,
            status="succeeded",
        )
    )
    reads, original = [], projections.read_run_content

    def output(db, row):
        reads.append(row.id)
        return original(db, row)

    monkeypatch.setattr(projections, "read_run_content", output)
    base = f"/api/conversations/{conversation['id']}"
    response = api_client.get(base + f"/questions/{question_id}/preview")
    assert response.status_code == 200
    preview = response.json()
    assert preview["question"] == "固定问题 用户原文"
    assert preview["answer"].startswith("最新回答 ") and len(preview["answer"]) == 480
    assert preview["question_id"] == question_id
    assert preview["response_id"] == run["id"]
    assert preview["status"] == "succeeded" and preview["version"] > run["version"]
    assert reads == [run["id"]]
    assert set(preview) == {
        "question_id",
        "question",
        "answer",
        "response_id",
        "status",
        "version",
    }
    assert api_client.get(base + "/questions").json()["total"] == 1
    assert api_client.get(base + f"/questions/{run['id']}/preview").status_code == 404
    assert api_client.get(base + "/questions/999999999999/preview").status_code == 404


def test_question_preview_cannot_cross_conversations_and_needs_run_read_permission(api_client):
    from app.errors import NotFoundError, PermissionDeniedError

    _, _, first = setup_agent(api_client)
    _, _, second = setup_agent(api_client)
    run = send(api_client, first).json()["response"]
    base = f"/api/conversations/{second['id']}"
    assert (
        api_client.get(base + f"/questions/{run['reply_to_message_id']}/preview").status_code == 404
    )
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    limited = replace(actor, role="preview-reader")
    ROLE_PERMISSIONS["preview-reader"] = {"conversations:read"}
    try:
        with pytest.raises(PermissionDeniedError):
            api_client.app.state.conversation_queries.question_preview(
                limited, first["id"], run["reply_to_message_id"]
            )
        with pytest.raises(NotFoundError):
            api_client.app.state.conversation_queries.question_preview(
                replace(limited, user_id=str(uuid4())), first["id"], run["reply_to_message_id"]
            )
    finally:
        ROLE_PERMISSIONS.pop("preview-reader")


def test_http_model_adapter_uses_fixed_config_and_normalizes_finish_and_usage(
    monkeypatch, tmp_path
):

    import httpx

    from app.execution.runtime.agent import execute_agent
    from app.execution.runtime.checkpoints import CheckpointStore
    from app.llm.config import LLMConfig

    real, calls = httpx.AsyncClient, []

    def handle(request):
        calls.append(request)
        body = json.loads(request.content)
        assert body["model"] == "model" and body["stream"] is True
        assert "系统提示" in str(body["messages"][0]["content"])
        assert body.get("max_completion_tokens", body.get("max_tokens")) == 4096
        parts = [
            {
                "id": "chat-test",
                "object": "chat.completion.chunk",
                "model": "model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "真实适配"},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "chat-test",
                "object": "chat.completion.chunk",
                "model": "model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        ]
        data = (
            "".join("data: " + json.dumps(part, ensure_ascii=False) + "\n\n" for part in parts)
            + "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=data, headers={"content-type": "text/event-stream"})

    class factory(real):
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
            super().__init__(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr("app.llm.factory.httpx.AsyncClient", factory)

    from runtime_helpers import MemoryContext

    snapshot = {
        "system_prompt": "系统提示",
        "memory_scope": "adapter-test",
        "memory_reset": False,
        "max_output_tokens": 4096,
        "skills": [],
        "selected_skill_ids": [],
        "recursion_limit": 64,
        "max_model_calls": 8,
        "max_skill_reads": 16,
        "context_bytes": 131072,
        "max_output_bytes": 131072,
        "max_reasoning_bytes": 32768,
    }
    input = AgentRequest(
        "test",
        snapshot,
        [{"id": "input", "role": "user", "content": "你好"}],
        LLMConfig(api_key="test-key", model_id="model", base_url="https://example.test/v1"),
        thread_id="test-thread",
    )
    result = asyncio.run(
        execute_agent(
            input, MemoryContext(), checkpoints=CheckpointStore(str(tmp_path / "adapter.db"))
        )
    )
    assert result.text == "真实适配" and result.usage["total_tokens"] == 5 and len(calls) == 1


def test_runtime_configuration_validates_limits():
    from app.execution.config import load_runtime_config

    config = load_runtime_config({"RUN_RUN_TIMEOUT": "0.5"})
    assert config.run_timeout == 0.5
    for value in ("0", "-1", "nan", "inf", "", None):
        with pytest.raises(ValueError):
            load_runtime_config({"RUN_RUN_TIMEOUT": value})


def test_runtime_budgets_freeze_on_submit_and_refresh_on_retry(api_client):
    _, _, conversation = setup_agent(api_client)
    service = api_client.app.state.conversation_commands
    original = {"recursion_limit": 40, "max_model_calls": 2, "max_skill_reads": 3}
    updated = {"recursion_limit": 72, "max_model_calls": 4, "max_skill_reads": 6}
    set_submission_limits(service, **original)
    key = str(uuid4())
    run = send(api_client, conversation, key=key).json()["response"]
    set_submission_limits(service, **updated)
    assert send(api_client, conversation, key=key).json()["response"]["id"] == run["id"]
    store = api_client.app.state.run_worker.store
    snapshot = store.load(run["id"])[0].config_snapshot
    assert {name: snapshot[name] for name in original} == original
    assert api_client.post(reply_path(api_client, run["id"]) + "/stop", json={}).status_code == 200
    retry = api_client.post(
        reply_path(api_client, run["id"]) + "/retry", json={"client_request_id": str(uuid4())}
    )
    assert retry.status_code == 202, retry.text
    snapshot = store.load(retry.json()["response"]["id"])[0].config_snapshot
    assert {name: snapshot[name] for name in updated} == updated


def test_shared_rules_freeze_per_submission_and_preserve_idempotency(api_client, monkeypatch):
    from test_capability_runtime import ScriptedModel, execute, response

    _, agent, first = setup_agent(api_client)
    _, other_agent, second = setup_agent(api_client)
    url = "/api/organization-rules"
    key = str(uuid4())
    old = send(api_client, first, key=key).json()["response"]
    store = api_client.app.state.run_worker.store
    old_row, _ = store.load(old["id"])
    assert old_row.config_snapshot["system_prompt"] == compose_system_prompt(
        "", agent["system_prompt"], agent_name=agent["name"]
    )
    assert old_row.config_snapshot["organization_rules"]["revision"] == 0
    rules = api_client.put(url, json={"instructions": "不要编造操作结果。", "revision": 0}).json()
    assert send(api_client, first, key=key).json()["response"]["id"] == old["id"]
    assert store.load(old["id"])[0].config_snapshot == old_row.config_snapshot
    api_client.post(reply_path(api_client, old["id"]) + "/stop", json={})
    retry = api_client.post(
        reply_path(api_client, old["id"]) + "/retry", json={"client_request_id": str(uuid4())}
    ).json()["response"]
    other = send(api_client, second).json()["response"]
    for run, current_agent in ((retry, agent), (other, other_agent)):
        row, _ = store.load(run["id"])
        snapshot = row.config_snapshot
        assert snapshot["schema_version"] == 5
        assert snapshot["organization_rules"] == rules
        assert snapshot["agent_system_prompt"] == agent["system_prompt"]
        assert snapshot["system_prompt"] == compose_system_prompt(
            rules["instructions"], current_agent["system_prompt"], agent_name=current_agent["name"]
        )
        assert "organization_rules" not in run and "config_snapshot" not in run
    assert (
        api_client.get(f"/api/agents/{other_agent['id']}").json()["system_prompt"]
        == other_agent["system_prompt"]
    )
    assert api_client.put(url, json={"instructions": "", "revision": 1}).status_code == 200
    assert store.load(other["id"])[0].config_snapshot["organization_rules"] == rules
    assert (
        execute(api_client, monkeypatch, ScriptedModel(responses=[response("已答复")]), other)[
            "status"
        ]
        == "succeeded"
    )
    next_run = send(api_client, second).json()["response"]
    assert store.load(next_run["id"])[0].config_snapshot["system_prompt"] == compose_system_prompt(
        "", other_agent["system_prompt"], agent_name=other_agent["name"]
    )


def test_compiled_rules_count_toward_context_limit_atomically(api_client):
    _, agent, conversation = setup_agent(api_client)
    api_client.put("/api/organization-rules", json={"instructions": "规则", "revision": 0})
    service = api_client.app.state.conversation_commands
    # Raw rule + agent + message fits; the required composition wrapper makes it too large.
    limit = len(("规则" + agent["system_prompt"] + "你好").encode())
    set_submission_limits(service, context_bytes=limit)
    failed = send(api_client, conversation)
    assert failed.status_code == 422 and failed.json()["detail"]["code"] == "context_limit_exceeded"
    assert api_client.get(f"/api/conversations/{conversation['id']}/messages").json()["items"] == []
    set_submission_limits(
        service,
        context_bytes=len(
            (
                compose_system_prompt("规则", agent["system_prompt"], agent_name=agent["name"])
                + "你好"
            ).encode()
        ),
    )
    assert send(api_client, conversation).status_code == 202


def test_runner_uses_frozen_rules_even_after_update(api_client):
    _, agent, conversation = setup_agent(api_client)
    api_client.put("/api/organization-rules", json={"instructions": "旧规则", "revision": 0})
    run = send(api_client, conversation).json()["response"]
    api_client.put("/api/organization-rules", json={"instructions": "新规则", "revision": 1})
    seen = []

    async def execute(input, hooks):
        seen.append(input.snapshot["system_prompt"])
        return AgentOutput("完成")

    set_executor(api_client, execute)
    asyncio.run(execute_run(api_client, run["id"]))
    assert "旧规则" in seen[0] and "新规则" not in seen[0]
    assert read_reply(api_client, run["id"])["status"] == "succeeded"


def test_current_executor_rejects_future_snapshot_protocol(api_client):
    _, _, conversation = setup_agent(api_client)
    run = send(api_client, conversation).json()["response"]
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, run["id"])
        future = {**row.config_snapshot, "schema_version": 999}
        row.config_snapshot = future

    async def unexpected_execution(input, hooks):
        pytest.fail("Unknown snapshot protocols must not be executed")

    set_executor(api_client, unexpected_execution)
    runner = api_client.app.state.run_worker
    asyncio.run(execute_run(api_client, run["id"]))
    result = read_reply(api_client, run["id"])
    assert result["status"] == "interrupted"
    assert result["error"]["code"] == "runtime_interrupted"
    assert runner.store.load(run["id"])[0].config_snapshot == future
