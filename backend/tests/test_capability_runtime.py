"""P1 acceptance through the real SDK, persistence and HTTP boundaries; no paid API calls."""

import asyncio
from uuid import uuid4

import pytest
from configuration_helpers import set_submission_limits
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr
from run_helpers import complete_run, empty_conversation, execute_run, read_reply, reply_path

from app.execution.models import Run


class ScriptedModel(BaseChatModel):
    responses: list[AIMessage]
    prompts: list[str] = Field(default_factory=list)
    bindings: list[list[str]] = Field(default_factory=list)
    _index: int = PrivateAttr(default=0)

    @property
    def _llm_type(self):
        return "p1-acceptance"

    def bind_tools(self, tools, **kwargs):
        self.bindings.append([getattr(t, "name", "unknown") for t in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append("\n".join(str(m.content) for m in messages))
        assert self._index < len(self.responses), "Unexpected model invocation"
        response = self.responses[self._index]
        self._index += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


def response(text="完成", tool_calls=None):
    return AIMessage(
        content=text,
        tool_calls=tool_calls or [],
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        response_metadata={"finish_reason": "tool_calls" if tool_calls else "stop"},
    )


def setup(client):
    skill = client.post(
        "/api/skills",
        json={
            "name": "审阅方法",
            "description": "按规则检查文档",
            "instructions": "BODY_MARKER_P1：逐项核对原文，再给结论。",
        },
    ).json()
    connection = client.post(
        "/api/model-connections",
        json={"name": "测试大脑", "api_key": "fixture-secret-never-output"},
    ).json()
    agent = client.post(
        "/api/agents",
        json={
            "name": "审阅员",
            "avatar_id": "admin",
            "model_connection_id": connection["id"],
            "skill_assignments": [{"skill_id": skill["id"]}],
        },
    ).json()
    conversation = empty_conversation(client, agent["id"])
    return skill, connection, agent, conversation


def submit(client, conversation, selected=None, key=None, content="请审阅文档"):
    data = {"content": content, "client_request_id": key or str(uuid4())}
    if selected is not None:
        data["selected_skill_ids"] = selected
    return client.post(f"/api/conversations/{conversation['id']}/messages", json=data)


def execute(client, monkeypatch, model, run):
    monkeypatch.setattr("app.llm.factory.create_chat_model", lambda *a, **k: model)
    asyncio.run(execute_run(client, run["id"]))
    client.app.state.conversation_acceptance.sweep()
    return read_reply(client, run["id"])


def test_real_sdk_automatic_activation_and_durable_evidence(api_client, monkeypatch):
    skill, _, _, conversation = setup(api_client)
    path = f"/skills/s-{skill['id']}/SKILL.md"
    model = ScriptedModel(
        responses=[
            response(
                "我先读取方法", [{"name": "read_file", "id": "read-1", "args": {"file_path": path}}]
            ),
            response("审阅结果"),
        ]
    )
    run = submit(api_client, conversation).json()["response"]
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "succeeded", result
    assert result["content"] == "审阅结果"
    assert result["usage"]["total_tokens"] == 30
    assert "BODY_MARKER_P1" not in model.prompts[0]
    assert "BODY_MARKER_P1" in model.prompts[1]
    assert all(tools == ["read_file"] for tools in model.bindings)
    steps = read_reply(api_client, run["id"])["steps"]
    assert [s["kind"] for s in steps] == [
        "model_call",
        "tool_call",
        "skill_activation",
        "model_call",
    ]
    assert all(s["status"] == "succeeded" and s["finished_at"] for s in steps)
    assert [s["sequence"] for s in steps] == [1, 2, 3, 4]
    model_steps = [s for s in steps if s["kind"] == "model_call"]
    assert [s["action_key"] for s in model_steps] == ["model:1", "model:2"]
    assert [s["safe_details"]["round"] for s in model_steps] == [1, 2]
    assert "fixture-secret-never-output" not in str(steps)


@pytest.mark.parametrize("missing_middle_usage", [False, True])
def test_usage_accumulates_across_tool_rounds(api_client, monkeypatch, missing_middle_usage):
    skill, _, _, conversation = setup(api_client)
    path = f"/skills/s-{skill['id']}/SKILL.md"
    responses = [
        response("", [{"name": "read_file", "id": f"read-{i}", "args": {"file_path": path}}])
        for i in range(2)
    ]
    if missing_middle_usage:
        responses[1] = responses[1].model_copy(update={"usage_metadata": None})
    model = ScriptedModel(responses=[*responses, response("审阅结果")])
    run = submit(api_client, conversation).json()["response"]
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "succeeded", result
    assert result["usage"]["total_tokens"] == (None if missing_middle_usage else 45)
    assert len(model.prompts) == 3
    assert all("BODY_MARKER_P1" in prompt for prompt in model.prompts[1:])
    steps = read_reply(api_client, run["id"])["steps"]
    assert [s["action_key"] for s in steps if s["kind"] == "model_call"] == [
        "model:1",
        "model:2",
        "model:3",
    ]
    assert len([s for s in steps if s["kind"] == "skill_activation"]) == 1


def test_explicit_pin_and_unrelated_greeting(api_client, monkeypatch):
    skill, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation, [skill["id"]]).json()["response"]
    model = ScriptedModel(responses=[response("按所选方法回答")])
    assert execute(api_client, monkeypatch, model, run)["status"] == "succeeded"
    assert "BODY_MARKER_P1" in model.prompts[0]
    assert [s["kind"] for s in read_reply(api_client, run["id"])["steps"]] == [
        "skill_activation",
        "model_call",
    ]
    greeting = submit(api_client, conversation, content="你好").json()["response"]
    model = ScriptedModel(responses=[response("你好，我可以帮你审阅文档。")])
    assert execute(api_client, monkeypatch, model, greeting)["status"] == "succeeded"
    # Official pin messages remain thread memory; they do not activate or charge this Run again.
    assert "BODY_MARKER_P1" in model.prompts[0]
    assert [s["kind"] for s in read_reply(api_client, greeting["id"])["steps"]] == ["model_call"]


@pytest.mark.parametrize("read_limit", [1, 2])
def test_parallel_skill_loads_share_budget_and_activate_once(api_client, monkeypatch, read_limit):
    skill, _, _, conversation = setup(api_client)
    path = f"/skills/s-{skill['id']}/SKILL.md"
    service = api_client.app.state.conversation_commands
    set_submission_limits(service, max_skill_reads=read_limit)
    run = submit(api_client, conversation).json()["response"]
    set_submission_limits(service, max_skill_reads=16)
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": "read_file",
                        "id": f"read-{i}",
                        "args": {"file_path": path, "offset": 1000, "limit": 1},
                    }
                    for i in range(2)
                ],
            ),
            response("按完整方法完成审阅"),
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    steps = read_reply(api_client, run["id"])["steps"]
    assert sum(s["kind"] == "skill_activation" for s in steps) == 1
    if read_limit == 1:
        assert result["status"] == "failed"
        assert result["error"]["code"] == "agent_budget_exceeded"
        assert len(model.prompts) == 1
    else:
        assert result["status"] == "succeeded", result
        assert "BODY_MARKER_P1" in model.prompts[1]
        assert result["usage"]["total_tokens"] == 30


def test_same_named_skills_keep_pinned_and_automatic_parameters_separate(api_client, monkeypatch):
    first, _, agent, conversation = setup(api_client)
    schema = {
        "type": "object",
        "properties": {"mode": {"type": "string"}},
        "additionalProperties": False,
    }
    assert (
        api_client.patch(
            f"/api/skills/{first['id']}",
            json={"expected_revision": 1, "configuration_schema": schema},
        ).status_code
        == 200
    )
    created = api_client.post(
        "/api/skills",
        json={
            "name": first["name"],
            "description": "另一个同名方法",
            "instructions": "SECOND_BODY_MARKER：检查措辞。",
            "configuration_schema": schema,
        },
    )
    assert created.status_code == 201
    second = created.json()
    assert (
        api_client.patch(
            f"/api/agents/{agent['id']}",
            json={
                "expected_revision": agent["revision"],
                "skill_assignments": [
                    {"skill_id": first["id"], "parameters": {"mode": "自动参数甲"}},
                    {"skill_id": second["id"], "parameters": {"mode": "显式参数乙"}},
                ],
            },
        ).status_code
        == 200
    )
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": "read_file",
                        "id": "load-first",
                        "args": {"file_path": f"/skills/s-{first['id']}/SKILL.md"},
                    }
                ],
            ),
            response("完成两种审阅"),
        ]
    )
    run = submit(api_client, conversation, [second["id"]]).json()["response"]
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "succeeded", result
    assert "SECOND_BODY_MARKER" in model.prompts[0] and "显式参数乙" in model.prompts[0]
    assert "BODY_MARKER_P1" not in model.prompts[0] and "自动参数甲" not in model.prompts[0]
    assert all(
        marker in model.prompts[1]
        for marker in ["BODY_MARKER_P1", "SECOND_BODY_MARKER", "自动参数甲", "显式参数乙"]
    )
    steps = read_reply(api_client, run["id"])["steps"]
    assert [
        (step["skill_id"], step["safe_details"]["source"])
        for step in steps
        if step["kind"] == "skill_activation"
    ] == [(second["id"], "explicit"), (first["id"], "automatic")]


def test_explicit_skill_requires_host_loaded_body_before_model(api_client, monkeypatch):
    from app.execution.runtime.skills import SkillsMiddleware

    async def skip_pinning(self, state, runtime):
        return None

    monkeypatch.setattr(SkillsMiddleware, "abefore_model", skip_pinning)
    skill, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation, [skill["id"]]).json()["response"]
    model = ScriptedModel(responses=[response("不能调用")])
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "failed" and result["error"]["code"] == "skill_load_failed"
    assert model.prompts == []
    assert read_reply(api_client, run["id"])["steps"] == []


def test_snapshot_is_fixed_and_selection_is_idempotent(api_client, monkeypatch):
    skill, _, _, conversation = setup(api_client)
    key = str(uuid4())
    run = submit(api_client, conversation, [skill["id"]], key).json()["response"]
    assert (
        submit(api_client, conversation, [skill["id"]], key).json()["response"]["id"] == run["id"]
    )
    assert submit(api_client, conversation, [], key).status_code == 409
    assert (
        api_client.patch(
            f"/api/skills/{skill['id']}", json={"expected_revision": 1, "instructions": "NEW_BODY"}
        ).status_code
        == 200
    )
    model = ScriptedModel(responses=[response()])
    assert execute(api_client, monkeypatch, model, run)["status"] == "succeeded"
    assert "BODY_MARKER_P1" in model.prompts[0] and "NEW_BODY" not in model.prompts[0]
    with api_client.app.state.database.transaction() as db:
        snapshot = db.get(Run, run["id"]).config_snapshot
    assert snapshot["schema_version"] == 5 and snapshot["skills"][0]["skill_revision"] == 1


def test_invalid_explicit_selection_has_no_run_or_messages(api_client):
    skill, _, agent, conversation = setup(api_client)
    path = f"/api/conversations/{conversation['id']}/messages"
    for selected in [None, [skill["id"], skill["id"].upper()]]:
        assert (
            api_client.post(
                path,
                json={
                    "content": "审阅",
                    "client_request_id": str(uuid4()),
                    "selected_skill_ids": selected,
                },
            ).status_code
            == 422
        )
    assert submit(api_client, conversation, [str(uuid4())]).status_code == 409
    assert (
        api_client.patch(
            f"/api/skills/{skill['id']}", json={"expected_revision": 1, "instructions": ""}
        ).status_code
        == 200
    )
    assert (
        submit(api_client, conversation, [skill["id"]]).json()["detail"]["code"]
        == "skill_not_ready"
    )
    assert api_client.get(f"/api/conversations/{conversation['id']}/messages").json()["items"] == []


def test_disabled_assignment_and_credential_rotation_prevent_calls(api_client, monkeypatch):
    skill, connection, agent, conversation = setup(api_client)
    run = submit(api_client, conversation, [skill["id"]]).json()["response"]
    assert (
        api_client.patch(
            f"/api/agents/{agent['id']}",
            json={
                "expected_revision": 1,
                "skill_assignments": [{"skill_id": skill["id"], "enabled": False}],
            },
        ).status_code
        == 200
    )
    model = ScriptedModel(responses=[])
    result = execute(api_client, monkeypatch, model, run)
    assert (
        result["status"] in ("failed", "cancelled")
        and result["error"]["code"] == "skill_access_revoked"
    )
    assert model.prompts == []
    run = submit(api_client, conversation).json()["response"]
    assert (
        api_client.patch(
            f"/api/model-connections/{connection['id']}",
            json={
                "expected_config_revision": 1,
                "expected_credential_revision": 1,
                "api_key": "rotated-dummy",
            },
        ).status_code
        == 200
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["error"]["code"] == "model_configuration_changed" and not model.prompts


@pytest.mark.parametrize(
    "path,error_code",
    [("/etc/passwd", "tool_not_allowed"), ("/skills/not-assigned/SKILL.md", "skill_not_allowed")],
)
def test_unapproved_path_and_false_model_claim_never_create_activation(
    api_client, monkeypatch, path, error_code
):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    model = ScriptedModel(responses=[response("我已执行全部技能")])
    assert execute(api_client, monkeypatch, model, run)["status"] == "succeeded"
    assert [s["kind"] for s in read_reply(api_client, run["id"])["steps"]] == ["model_call"]
    run = submit(api_client, conversation).json()["response"]
    model = ScriptedModel(
        responses=[
            response("", [{"name": "read_file", "id": "bad-path", "args": {"file_path": path}}])
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "failed" and result["error"]["code"] == error_code
    assert len(model.prompts) == 1
    assert not any(
        s["kind"] == "skill_activation" for s in read_reply(api_client, run["id"])["steps"]
    )


def test_model_budget_and_usage_on_failure(api_client, monkeypatch):
    skill, _, _, conversation = setup(api_client)
    path = f"/skills/s-{skill['id']}/SKILL.md"
    service = api_client.app.state.conversation_commands
    set_submission_limits(service, max_model_calls=2)
    run = submit(api_client, conversation).json()["response"]
    set_submission_limits(service, max_model_calls=8)
    model = ScriptedModel(
        responses=[
            response("", [{"name": "read_file", "id": f"read-{i}", "args": {"file_path": path}}])
            for i in range(3)
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "failed" and result["error"]["code"] == "agent_budget_exceeded"
    assert len(model.prompts) == 2 and result["usage"]["total_tokens"] == 30
    assert (
        sum(s["kind"] == "skill_activation" for s in read_reply(api_client, run["id"])["steps"])
        == 1
    )


@pytest.mark.parametrize("limit", [1, 64])
def test_real_sdk_uses_frozen_graph_budget(api_client, monkeypatch, limit):
    _, _, _, conversation = setup(api_client)
    service = api_client.app.state.conversation_commands
    set_submission_limits(service, recursion_limit=limit)
    run = submit(api_client, conversation).json()["response"]
    set_submission_limits(service, recursion_limit=128)
    model = ScriptedModel(responses=[response("完成")])
    result = execute(api_client, monkeypatch, model, run)
    if limit == 1:
        assert result["status"] == "failed"
        assert result["error"]["code"] == "agent_budget_exceeded"
        assert model.prompts == []
    else:
        assert result["status"] == "succeeded", result
        assert len(model.prompts) == 1


def test_restart_action_dedup_pagination_and_guest_scope(api_client, migrated_config):
    import pytest
    from fastapi.testclient import TestClient

    from app.bootstrap import create_app
    from app.errors import ConflictError

    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    assert store.claim(run["id"])
    store.start_action(run["id"], "model:1", "model_call", {"round": 1})
    with pytest.raises(ConflictError):
        store.start_action(run["id"], "model:1", "model_call")
    for intent in store.recover():
        complete_run(api_client)(intent)
    result = read_reply(api_client, run["id"])
    assert result["status"] == "interrupted"
    steps = read_reply(api_client, run["id"])["steps"]
    assert len(steps) == 1 and steps[0]["status"] == "unknown"
    with TestClient(create_app(migrated_config), headers=api_client.headers) as guest:
        guest.post("/api/auth/guest", json={})
        assert guest.get(reply_path(guest, run["id"])).status_code == 403
        assert guest.get(reply_path(guest, run["id"]) + "/events").status_code == 403


def test_step_storage_failure_never_calls_model_or_reports_success(api_client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    model = ScriptedModel(responses=[response()])

    def fail(*args, **kwargs):
        raise OperationalError("fixture", {}, Exception("fixture"))

    monkeypatch.setattr(store, "_start_action", fail)
    # A direct Task reports storage failure; Worker coordination owns its retry.
    with pytest.raises(OperationalError):
        execute(api_client, monkeypatch, model, run)
    result = read_reply(api_client, run["id"])
    assert result["status"] != "succeeded" and not model.prompts
    for intent in store.recover():
        complete_run(api_client)(intent)
    assert read_reply(api_client, run["id"])["status"] == "interrupted"


def test_revocation_after_activation_blocks_next_model(api_client, monkeypatch):
    skill, _, agent, conversation = setup(api_client)
    path = f"/skills/s-{skill['id']}/SKILL.md"
    run = submit(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    finish = store.finish_action

    def revoke_after_activation(id, key, *args, **kwargs):
        finish(id, key, *args, **kwargs)
        if key.startswith("skill:"):
            assert (
                api_client.patch(
                    f"/api/agents/{agent['id']}",
                    json={"expected_revision": 1, "skill_assignments": []},
                ).status_code
                == 200
            )

    monkeypatch.setattr(store, "finish_action", revoke_after_activation)
    model = ScriptedModel(
        responses=[
            response("", [{"name": "read_file", "id": "load", "args": {"file_path": path}}]),
            response("不可调用"),
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert (
        result["status"] in ("failed", "cancelled")
        and result["error"]["code"] == "skill_access_revoked"
    )
    assert len(model.prompts) == 1 and result["content"] == ""
    assert result["usage"]["total_tokens"] == 15


def test_real_sdk_cancel_closes_running_model_step(api_client, monkeypatch):
    started, cleaned = asyncio.Event(), asyncio.Event()

    class WaitingModel(ScriptedModel):
        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    monkeypatch.setattr(
        "app.llm.factory.create_chat_model", lambda *a, **k: WaitingModel(responses=[])
    )

    async def cancel():
        task = asyncio.create_task(execute_run(api_client, run["id"]))
        await asyncio.wait_for(started.wait(), 3)
        cancelled = await asyncio.to_thread(
            api_client.post, reply_path(api_client, run["id"]) + "/stop", json={}
        )
        assert cancelled.status_code == 200
        await asyncio.wait_for(task, 3)

    asyncio.run(cancel())
    result = read_reply(api_client, run["id"])
    assert result["status"] == "cancelled" and cleaned.is_set()
    steps = read_reply(api_client, run["id"])["steps"]
    assert len(steps) == 1 and steps[0]["status"] == "unknown" and steps[0]["finished_at"]


def test_schema_4_credential_revision_and_unknown_usage(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    model = ScriptedModel(
        responses=[
            AIMessage(content="没有用量的实际响应", response_metadata={"finish_reason": "stop"})
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "succeeded" and result["usage"]["total_tokens"] is None
    with api_client.app.state.database.transaction() as db:
        snapshot = db.get(Run, run["id"]).config_snapshot
        assert (
            snapshot["connection_config_revision"]
            == snapshot["connection_credential_revision"]
            == 1
        )
        assert "connection_updated_at" not in snapshot
        assert "fixture-secret-never-output" not in str(snapshot)


def test_p1_backup_restore_and_historical_step_reference(api_client, monkeypatch, tmp_path):
    import sqlite3

    skill, _, agent, conversation = setup(api_client)
    run = submit(api_client, conversation, [skill["id"]]).json()["response"]
    model = ScriptedModel(responses=[response()])
    assert execute(api_client, monkeypatch, model, run)["status"] == "succeeded"
    source_path = api_client.app.state.database.engine.url.database
    backup_path, restored_path = tmp_path / "snapshot.sqlite3", tmp_path / "restored.sqlite3"
    with sqlite3.connect(source_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
    with sqlite3.connect(backup_path) as backup, sqlite3.connect(restored_path) as restored:
        backup.backup(restored)
    with sqlite3.connect(source_path) as source, sqlite3.connect(restored_path) as restored:
        tables = [
            row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        for table in tables:
            assert sorted(
                source.execute(f'SELECT * FROM "{table}"').fetchall(), key=repr
            ) == sorted(restored.execute(f'SELECT * FROM "{table}"').fetchall(), key=repr)
        assert restored.execute("PRAGMA foreign_key_check").fetchall() == []
        assert restored.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    # Deleting a now-unassigned definition preserves the actual historical action's summary.
    assert (
        api_client.patch(
            f"/api/agents/{agent['id']}",
            json={"expected_revision": 1, "skill_assignments": []},
        ).status_code
        == 200
    )
    assert api_client.delete(f"/api/skills/{skill['id']}").status_code == 204
    activation = next(
        s for s in read_reply(api_client, run["id"])["steps"] if s["kind"] == "skill_activation"
    )
    assert activation["skill_id"] is None and activation["safe_details"]["name"] == skill["name"]


def test_explicit_loading_shares_the_method_read_budget(api_client, monkeypatch):
    skill, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation, [skill["id"]]).json()["response"]
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, run["id"])
        row.config_snapshot = {**row.config_snapshot, "max_skill_reads": 1}
    path = f"/skills/s-{skill['id']}/SKILL.md"
    model = ScriptedModel(
        responses=[
            response("", [{"name": "read_file", "id": "again", "args": {"file_path": path}}])
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "failed" and result["error"]["code"] == "agent_budget_exceeded"
    assert len(model.prompts) == 1
    assert submit(api_client, conversation, [str(uuid4()) for _ in range(17)]).status_code == 422


def test_failed_unreported_model_call_does_not_claim_complete_usage(api_client, monkeypatch):
    skill, _, _, conversation = setup(api_client)
    path = f"/skills/s-{skill['id']}/SKILL.md"
    run = submit(api_client, conversation).json()["response"]
    # The second real SDK invocation raises before a usage-bearing response exists.
    model = ScriptedModel(
        responses=[response("", [{"name": "read_file", "id": "load", "args": {"file_path": path}}])]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "failed" and result["usage"]["total_tokens"] is None
    steps = read_reply(api_client, run["id"])["steps"]
    assert [s["status"] for s in steps] == ["succeeded", "succeeded", "succeeded", "failed"]
