"""Evidence is related to real actions, private, bounded, and independent of delivery."""

import asyncio
import json
import logging
import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from run_helpers import execute_run, read_reply, reply_path
from sqlalchemy import func, select
from test_capability_runtime import setup, submit

from app.errors import NotFoundError, PermissionDeniedError
from app.execution.evidence import document
from app.execution.models import Run, RunAction
from app.files.models import StoredFile
from app.infrastructure.observability import ExecutionLogs, run_id_context
from app.values import utc_now


def local_transport(monkeypatch, upstream):
    real = httpx.AsyncClient

    class LocalClient(real):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(upstream), **kwargs)

    monkeypatch.setattr("app.llm.factory.httpx.AsyncClient", LocalClient)


def stream(delta, reason="stop"):
    chunks = [
        {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {
            "choices": [{"index": 0, "delta": {}, "finish_reason": reason}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
        },
    ]
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text="".join(
            "data: "
            + json.dumps({"id": "local", "object": "chat.completion.chunk", **item})
            + "\n\n"
            for item in chunks
        )
        + "data: [DONE]\n\n",
    )


def test_real_two_round_wire_tool_feedback_and_private_query(api_client, monkeypatch, tmp_path):
    skill, _, _, conversation = setup(api_client)
    run_id = submit(api_client, conversation).json()["response"]["id"]
    requests = []

    def upstream(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return stream(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "skill-read",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps(
                                    {"file_path": f"/skills/s-{skill['id']}/SKILL.md"}
                                ),
                            },
                        }
                    ],
                },
                "tool_calls",
            )
        return stream({"content": "已按审阅方法完成"})

    local_transport(monkeypatch, upstream)
    logs = ExecutionLogs(tmp_path / "logs")
    close = logs.install()
    try:
        asyncio.run(execute_run(api_client, run_id))
    finally:
        close()
    api_client.app.state.conversation_acceptance.sweep()
    assert read_reply(api_client, run_id)["status"] == "succeeded"
    assert len(requests) == 2
    assert any(
        m["role"] == "tool" and "BODY_MARKER_P1" in str(m["content"])
        for m in requests[1]["messages"]
    )
    path = reply_path(api_client, run_id) + "/trace"
    first = api_client.get(path)
    assert first.status_code == 200 and first.headers["cache-control"] == "no-store"
    trace = first.json()
    actions = trace["actions"]["items"]
    assert [a["kind"] for a in actions] == [
        "model_call",
        "tool_call",
        "skill_activation",
        "model_call",
    ]
    assert trace["selected"]["request"]["document"]["payload"] == requests[0]
    tool = actions[1]
    assert tool["parent_action_id"] == actions[0]["id"]
    selected = api_client.get(path, params={"action_id": tool["id"]}).json()["selected"]
    assert selected["request"]["document"]["payload"]["requested_arguments"]["file_path"].endswith(
        "SKILL.md"
    )
    assert selected["request"]["document"]["payload"]["effective_arguments"]["limit"] == 1000000
    assert selected["request"]["document"]["payload"]["authorization_status"] == "allowed"
    assert "BODY_MARKER_P1" in selected["response"]["document"]["payload"]["content"]
    last = api_client.get(path, params={"action_id": actions[-1]["id"]}).json()["selected"]
    assert last["request"]["document"]["payload"] == requests[1]
    assert last["response"]["document"]["capture_stage"] == "sdk_response"
    download = api_client.get(path + f"/actions/{actions[-1]['id']}/evidence/request")
    assert download.status_code == 200 and download.json()["payload"] == requests[1]
    assert "fixture-secret-never-output" not in download.text
    assert logs.read(run_id)["items"] and any(
        item["action_key"] == "tool:skill-read" for item in logs.read(run_id)["items"]
    )
    assert (
        api_client.get(f"/api/conversations/{conversation['id']}/trace").json()["run"]["id"]
        == run_id
    )
    assert api_client.get(path, params={"action_id": str(uuid4())}).status_code == 404
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    member = replace(actor, role="member")
    queries = api_client.app.state.execution_queries
    limited = queries.read(member, run_id)
    assert (
        not limited["can_inspect_inputs"]
        and limited["selected"]["request"]["status"] == "restricted"
    )
    with pytest.raises(PermissionDeniedError):
        queries.download(member, run_id, actions[0]["id"], "request")
    with pytest.raises(NotFoundError):
        queries.read(replace(member, user_id=str(uuid4())), run_id)
    with pytest.raises(PermissionDeniedError):
        queries.read(replace(actor, role="guest"), run_id)
    with api_client.app.state.database.transaction() as db:
        files = list(db.scalars(select(StoredFile).where(StoredFile.purpose == "evidence")))
        assert files
        for file in files:
            with pytest.raises(NotFoundError):
                api_client.app.state.files.capture(
                    db, [file.id], actor.user_id, allowed_ids=[file.id]
                )
            assert (
                api_client.get(
                    f"/api/conversations/{conversation['id']}/files/{file.id}"
                ).status_code
                == 404
            )
    assert all(f["purpose"] != "evidence" for f in api_client.app.state.files.sources(run_id))


def test_evidence_failure_leaves_conversation_success_and_original_tool_cache(
    api_client, monkeypatch
):
    skill, _, _, conversation = setup(api_client)
    run_id = submit(api_client, conversation).json()["response"]["id"]
    from test_capability_runtime import ScriptedModel, response

    model = ScriptedModel(responses=[response("完成")])
    monkeypatch.setattr("app.llm.factory.create_chat_model", lambda *a, **k: model)
    monkeypatch.setattr(
        api_client.app.state.run_worker.store,
        "save_evidence",
        lambda *a: (_ for _ in ()).throw(OSError("injected")),
    )
    asyncio.run(execute_run(api_client, run_id))
    api_client.app.state.conversation_acceptance.sweep()
    assert read_reply(api_client, run_id)["status"] == "succeeded"
    trace = api_client.get(reply_path(api_client, run_id) + "/trace").json()
    assert trace["selected"]["request"]["status"] == "not_collected"
    assert trace["selected"]["response"]["status"] == "not_collected"


def test_evidence_transaction_rollback_retention_and_isolated_quota(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    run_id = submit(api_client, conversation).json()["response"]["id"]
    store, files = api_client.app.state.run_worker.store, api_client.app.state.files
    store.claim(run_id)
    _, key = store.start_model(run_id, lambda db: None)
    original = files.register

    def fail_after_register(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("rollback")

    monkeypatch.setattr(files, "register", fail_after_register)
    with pytest.raises(OSError):
        store.save_evidence(run_id, key, "request", document("wire_request", {"messages": []}))
    with store.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(StoredFile)) == 0
        assert db.scalar(select(RunAction.request_file_id)) is None
    monkeypatch.setattr(files, "register", original)
    store.save_evidence(run_id, key, "request", document("wire_request", {"messages": []}))
    with store.database.transaction() as db:
        row = db.get(Run, run_id)
        row.status, row.finished_at = "succeeded", utc_now()
        action = db.scalar(select(RunAction).where(RunAction.run_id == run_id))
        action.status, action.finished_at = "succeeded", utc_now()
        held = action.request_file_id
        for file in db.scalars(select(StoredFile)):
            file.created_at = utc_now() - timedelta(days=2)
    from app.execution.store import retained_file_ids

    for file in files.directory.iterdir():
        os.utime(file, (0, 0))
    api_client.app.state.file_cleanup.sweep(retained_file_ids)
    with store.database.transaction() as db:
        assert db.get(StoredFile, held) is not None
    assert len(list(files.directory.iterdir())) == 1
    # Evidence quota is separate from uploaded inputs; exhaustion does not consume input quota.
    files.config = replace(files.config, max_evidence_owner_bytes=1)
    with pytest.raises(Exception) as caught:
        files.save(
            store.load(run_id)[0].owner_user_id,
            "large.json",
            b"{}",
            purpose="evidence",
            run_id=run_id,
        )
    assert caught.value.code == "file_quota_exceeded"
    assert files.save(store.load(run_id)[0].owner_user_id, "input.txt", b"ok")["purpose"] == "input"


def test_technical_logs_rotate_and_do_not_store_messages_or_exception_values(tmp_path):
    logs = ExecutionLogs(tmp_path)
    close = logs.install()
    logger = logging.getLogger("app.execution.runtime.task")
    token = run_id_context.set("100000000123")
    try:
        logger.warning(
            "execution.failed secret=%s",
            "DO_NOT_STORE",
            extra={"action_key": "model:1", "error_code": "upstream_unavailable"},
        )
    finally:
        run_id_context.reset(token)
        close()
    assert "DO_NOT_STORE" not in (tmp_path / "execution.jsonl").read_text()
    assert logs.read("100000000123")["items"][0]["action_key"] == "model:1"
    assert logs.read("100000000124")["items"] == []


def test_0024_preserves_file_bytes_metadata_and_old_actions(api_client, monkeypatch):
    # Exercise a populated upgrade from 0023 in a second isolated database using
    # frozen DDL and SQL inserts, so current ORM columns cannot mask the old schema.
    import sqlite3

    source = api_client.app.state.database.engine.url.database
    path = Path(source).with_name("before-evidence.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{path}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0023")
    with sqlite3.connect(source) as current, sqlite3.connect(path) as old:
        # Copy only credential-free user identity and a file; keep IDs and hashes intact.
        user = current.execute("select id from users limit 1").fetchone()[0]
        old.execute(
            "insert into users (id,username,password_hash,role,is_active) select ?,?,?,?,?",
            (user, "old", "hash", "admin", 1),
        )
        old.execute(
            "insert into stored_files(id,owner_user_id,name,media_type,size,content_hash,storage_key,purpose) values(?,?,?,?,?,?,?,?)",
            (str(uuid4()), user, "old.txt", "text/plain", 2, "hash", "original-key", "input"),
        )
        before = old.execute("select * from stored_files").fetchall()
    command.upgrade(config, "head")
    command.check(config)
    with sqlite3.connect(path) as db:
        assert db.execute("select * from stored_files").fetchall() == before
        assert db.execute("pragma foreign_key_check").fetchall() == []
        assert {"request_file_id", "response_file_id"} <= {
            row[1] for row in db.execute("pragma table_info(run_actions)")
        }


def test_readonly_retry_evidence_targets_new_attempt_and_cached_result_stays_compatible(api_client):
    from runtime_helpers import make_task

    from app.execution.contracts import ToolInvocation, ToolOutcome

    _, _, _, conversation = setup(api_client)
    run_id = submit(api_client, conversation).json()["response"]["id"]
    store = api_client.app.state.run_worker.store
    store.claim(run_id)
    control = make_task(
        run_id,
        store,
        lambda active, **kwargs: {"recovery": "readonly", "scope_policy": {"max_calls": 10}},
    )
    invocation = ToolInvocation("tool:retry", "fixture-binding", "lookup", {"query": "original"})

    async def scenario():
        first = await control.begin_tool(invocation)
        await control.capture_evidence(
            invocation.key, "request", "tool_request", {"attempt": "first"}
        )
        store.finish_action(run_id, first.action_key, "failed", "tool_upstream_failed")
        second = await control.begin_tool(invocation)
        assert second.action_key != first.action_key
        await control.capture_evidence(
            invocation.key, "request", "tool_request", {"attempt": "second"}
        )
        await control.complete_tool(second, ToolOutcome("saved feedback", data={"value": 1}))
        cached = await control.begin_tool(invocation)
        assert cached.action_key == second.action_key
        assert cached.cached == {
            "content": "saved feedback",
            "status": "succeeded",
            "data": {"value": 1},
        }

    asyncio.run(scenario())
    with store.database.transaction() as db:
        actions = list(
            db.scalars(
                select(RunAction).where(RunAction.kind == "tool_call").order_by(RunAction.sequence)
            )
        )
        assert len(actions) == 2
        contents = [
            json.loads(api_client.app.state.files.read(action.request_file_id))["payload"]
            for action in actions
        ]
        assert contents == [{"attempt": "first"}, {"attempt": "second"}]


def test_request_observers_are_task_local_and_reset_after_scope():
    from app.llm.factory import _capture_request, observe_model_request

    received = {"first": [], "second": []}

    async def scenario():
        ready = asyncio.Event()

        async def task(name):
            async def capture(payload):
                received[name].append(payload)

            with observe_model_request(capture):
                if name == "second":
                    ready.set()
                await ready.wait()
                await _capture_request(
                    httpx.Request("POST", "https://fixture.invalid", json={"name": name})
                )
            await _capture_request(
                httpx.Request("POST", "https://fixture.invalid", json={"outside": name})
            )

        await asyncio.gather(task("first"), task("second"))

    asyncio.run(scenario())
    assert received == {"first": [{"name": "first"}], "second": [{"name": "second"}]}


def test_redaction_preserves_unmodified_json_text_and_removes_nested_credentials():
    original = '[{"name":"lookup","arguments":{"query":"hello"}}]'
    assert document("sdk_response", {"content": original})["payload"]["content"] == original
    private = {
        "headers": {"Authorization": "Bearer SECRET"},
        "arguments": {"api_key": "SECRET"},
        "content": '{"password":"SECRET","value":1}',
    }
    assert "SECRET" not in json.dumps(document("tool_response", private))
    assert private["arguments"]["api_key"] == "SECRET"


def test_log_directory_failure_is_independent_of_application_startup(tmp_path):
    path = tmp_path / "not-a-directory"
    path.write_text("occupied")
    close = ExecutionLogs(path).install()
    close()
    assert ExecutionLogs(path).read("100000000123")["items"] == []


def test_visible_provider_reasoning_obeys_existing_budget():
    from langchain_core.messages import AIMessage

    from app.execution.runtime.streaming import RunProgress

    progress = RunProgress(100, 6)
    result = progress.record(
        "model:1",
        AIMessage(content="答复", additional_kwargs={"reasoning_content": "公开说明：按规则核对"}),
        complete=True,
    )
    assert result.reasoning_text == "公开" and result.reasoning_truncated
    assert (
        progress.record("model:2", AIMessage(content="第二轮"), complete=True).reasoning_text == ""
    )


def test_rotated_logs_are_still_found_by_same_run(tmp_path):
    from logging.handlers import RotatingFileHandler

    logs = ExecutionLogs(tmp_path)
    close = logs.install()
    logger = logging.getLogger("app.execution.runtime.task")
    handler = next(
        handler
        for handler in logging.getLogger("app").handlers
        if isinstance(handler, RotatingFileHandler)
        and handler.baseFilename == str(tmp_path / "execution.jsonl")
    )
    handler.maxBytes = 400
    token = run_id_context.set("100000000123")
    try:
        for index in range(3):
            logger.info("model.started", extra={"action_key": f"model:{index}"})
    finally:
        run_id_context.reset(token)
        close()
    assert (tmp_path / "execution.jsonl.1").exists()
    assert [item["action_key"] for item in logs.read("100000000123")["items"]] == [
        "model:0",
        "model:1",
        "model:2",
    ]


def test_failure_location_is_independent_of_action_paging(api_client):
    _, _, _, conversation = setup(api_client)
    run_id = submit(api_client, conversation).json()["response"]["id"]
    store = api_client.app.state.run_worker.store
    assert store.claim(run_id)
    first = store.start_action(run_id, "knowledge:first", "knowledge", {"query": "制度"})
    store.finish_action(run_id, "knowledge:first")
    failed = store.start_action(run_id, "model:failed", "model_call", {"round": 1})
    store.finish_action(run_id, "model:failed", "failed", "upstream_stream_error")
    path = f"/api/conversations/{conversation['id']}/responses/{run_id}/trace"
    result = api_client.get(path, params={"limit": 1}).json()
    assert len(result["actions"]["items"]) == 1
    assert result["actions"]["items"][0]["action_key"] == first
    assert result["failures"]["total"] == 1
    assert result["failures"]["items"][0]["action_key"] == failed
    assert result["selected"]["id"] == result["failures"]["items"][0]["id"]
    first_id = result["actions"]["items"][0]["id"]
    explicit = api_client.get(path, params={"limit": 1, "action_id": first_id}).json()
    assert explicit["selected"]["id"] == first_id


def test_model_metrics_use_captured_usage_and_respect_diagnostic_access(api_client):
    _, _, _, conversation = setup(api_client)
    run_id = submit(api_client, conversation).json()["response"]["id"]
    store = api_client.app.state.run_worker.store
    assert store.claim(run_id)
    key = store.start_action(run_id, "model:summary", "model_call", {"purpose": "summary"})
    store.save_evidence(
        run_id, key, "request", document("wire_request", {"max_tokens": 4096, "messages": []})
    )
    store.save_evidence(
        run_id,
        key,
        "response",
        document(
            "sdk_response",
            {
                "content": "partial",
                "usage": {
                    "input_tokens": 6722,
                    "output_tokens": 4096,
                    "total_tokens": 10818,
                    "output_token_details": {"reasoning": 3922},
                },
            },
        ),
    )
    store.finish_action(
        run_id, key, "failed", "output_limit_exceeded", details={"purpose": "summary"}
    )
    path = f"/api/conversations/{conversation['id']}/responses/{run_id}/trace"
    result = api_client.get(path).json()
    metrics = result["actions"]["items"][0]["metrics"]
    assert metrics == {
        "usage": {
            "input_tokens": 6722,
            "output_tokens": 4096,
            "total_tokens": 10818,
            "reasoning_tokens": 3922,
        },
        "usage_source": "response",
        "output_limit": 4096,
        "output_limit_field": "max_tokens",
    }
    assert result["failures"]["items"][0]["metrics"] == metrics
    assert result["selected"]["metrics"] == metrics
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    limited = api_client.app.state.execution_queries.read(replace(actor, role="member"), run_id)
    private_metrics = limited["selected"]["metrics"]
    assert private_metrics["output_limit"] is None
    assert all(value is None for value in private_metrics["usage"].values())
    store.save_evidence(
        run_id,
        key,
        "response",
        document("sdk_response", {"content": "x" * (256 * 1024), "usage": {"output_tokens": 4096}}),
    )
    truncated = api_client.get(path).json()["selected"]
    assert truncated["response"]["truncated"]
    assert truncated["metrics"]["usage_source"] is None
    assert truncated["metrics"]["usage"]["output_tokens"] is None
    assert truncated["metrics"]["output_limit"] == 4096
