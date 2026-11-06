"""Continuous SDK threads retain memory while business attempts remain independent."""

import asyncio

from configuration_helpers import set_submission_limits
from fastapi.testclient import TestClient
from run_helpers import checkpoint_store, empty_conversation, execute_run
from test_capability_runtime import ScriptedModel, response
from test_response_contract import employee, submit
from test_response_contract import wire as wire

from app.bootstrap import create_app
from app.execution.models import Run


def execute(client, monkeypatch, model, accepted):
    value = accepted.json()
    assert accepted.status_code == 202, value
    id = value["response"]["id"]
    monkeypatch.setattr("app.llm.factory.create_chat_model", lambda *args, **kwargs: model)
    asyncio.run(execute_run(client, id))
    client.app.state.conversation_acceptance.sweep()
    with client.app.state.database.transaction() as db:
        return db.get(Run, id)


def test_second_turn_uses_same_thread_after_new_backend_instance(
    wire, migrated_config, monkeypatch
):
    agent = employee(wire)
    conversation = empty_conversation(wire, agent["id"])["id"]
    first = execute(
        wire,
        monkeypatch,
        ScriptedModel(responses=[response("FIRST_ANSWER")]),
        submit(wire, conversation, agent, content="FIRST_QUESTION"),
    )
    assert first.status == "succeeded" and first.checkpoint_id
    with TestClient(
        create_app(migrated_config), headers={"Origin": "http://localhost:3000"}
    ) as second_client:
        second_client.cookies.update(wire.cookies)
        model = ScriptedModel(responses=[response("SECOND_ANSWER")])
        second = execute(
            second_client,
            monkeypatch,
            model,
            submit(second_client, conversation, agent, content="SECOND_QUESTION"),
        )
        assert second.status == "succeeded", second.error_code
        assert second.id != first.id and second.thread_id == first.thread_id
        assert second.base_checkpoint_id == first.checkpoint_id
        assert [item["content"] for item in second.input_snapshot] == ["SECOND_QUESTION"]
        assert model.prompts[0].count("FIRST_QUESTION") == 1
        assert model.prompts[0].count("FIRST_ANSWER") == 1
        assert second.model_calls == 1 and second.usage["total_tokens"] == 15
        history = second_client.get(f"/api/conversations/{conversation}/messages").json()["items"]
        assert [item["content"] for item in history] == [
            "FIRST_QUESTION",
            "FIRST_ANSWER",
            "SECOND_QUESTION",
            "SECOND_ANSWER",
        ]


def test_failed_thread_branch_is_not_used_by_next_turn(wire, monkeypatch):
    agent = employee(wire)
    conversation = empty_conversation(wire, agent["id"])["id"]
    first = execute(
        wire,
        monkeypatch,
        ScriptedModel(responses=[response("GOOD_ANSWER")]),
        submit(wire, conversation, agent, content="GOOD_QUESTION"),
    )
    failed = execute(
        wire,
        monkeypatch,
        ScriptedModel(responses=[response("")]),
        submit(wire, conversation, agent, content="FAILED_QUESTION"),
    )
    assert failed.status == "failed" and failed.checkpoint_id
    model = ScriptedModel(responses=[response("THIRD_ANSWER")])
    third = execute(
        wire, monkeypatch, model, submit(wire, conversation, agent, content="THIRD_QUESTION")
    )
    assert third.status == "succeeded", third.error_code
    assert third.base_run_id == first.id
    assert "GOOD_ANSWER" in model.prompts[0] and "FAILED_QUESTION" not in model.prompts[0]


def test_official_summary_persists_without_modifying_display_history(wire, monkeypatch):
    agent = employee(wire)
    conversation = empty_conversation(wire, agent["id"])["id"]
    original = "ORIGINAL_HISTORY_" * 250
    execute(
        wire,
        monkeypatch,
        ScriptedModel(responses=[response(original)]),
        submit(wire, conversation, agent, content="先记录目标"),
    )
    set_submission_limits(
        wire.app.state.conversation_commands, summary_trigger_tokens=200, summary_keep_tokens=40
    )
    model = ScriptedModel(responses=[response("SUMMARY_MARKER：目标和进展"), response("SECOND")])
    second = execute(
        wire, monkeypatch, model, submit(wire, conversation, agent, content="继续处理")
    )
    assert second.status == "succeeded", second.error_code
    assert second.model_calls == 2 and second.usage["total_tokens"] == 30
    assert "ORIGINAL_HISTORY_" in model.prompts[0]
    assert "SUMMARY_MARKER" in model.prompts[1]
    next_model = ScriptedModel(responses=[response("THIRD")])
    third = execute(
        wire, monkeypatch, next_model, submit(wire, conversation, agent, content="接着说")
    )
    assert third.status == "succeeded", third.error_code
    assert "SUMMARY_MARKER" in next_model.prompts[0]
    assert "ORIGINAL_HISTORY_" not in next_model.prompts[0]
    history = wire.get(f"/api/conversations/{conversation}/messages").json()["items"]
    assert history[1]["content"] == original


def test_summary_budget_blocks_answer_without_publishing_summary(wire, monkeypatch):
    agent = employee(wire)
    conversation = empty_conversation(wire, agent["id"])["id"]
    execute(
        wire,
        monkeypatch,
        ScriptedModel(responses=[response("LONG_" * 700)]),
        submit(wire, conversation, agent, content="保存任务目标"),
    )
    set_submission_limits(
        wire.app.state.conversation_commands,
        summary_trigger_tokens=200,
        summary_keep_tokens=40,
        max_model_calls=1,
    )
    model = ScriptedModel(responses=[response("内部摘要"), response("不应生成")])
    failed = execute(wire, monkeypatch, model, submit(wire, conversation, agent, content="继续"))
    assert failed.status == "failed" and failed.error_code == "agent_budget_exceeded"
    assert len(model.prompts) == 1 and failed.model_calls == 1
    history = wire.get(f"/api/conversations/{conversation}/messages").json()["items"]
    assert all(item["content"] != "内部摘要" for item in history)


def test_missing_thread_checkpoint_does_not_silently_rebuild_history(wire, monkeypatch):
    agent = employee(wire)
    conversation = empty_conversation(wire, agent["id"])["id"]
    execute(
        wire,
        monkeypatch,
        ScriptedModel(responses=[response("已完成回答")]),
        submit(wire, conversation, agent, content="第一问"),
    )
    checkpoint_store(wire).path.unlink()
    model = ScriptedModel(responses=[response("不应执行")])
    failed = execute(wire, monkeypatch, model, submit(wire, conversation, agent, content="追问"))
    assert failed.status == "interrupted" and failed.error_code == "checkpoint_unavailable"
    assert not model.prompts
    history = wire.get(f"/api/conversations/{conversation}/messages").json()["items"]
    assert history[1]["content"] == "已完成回答"


def test_summary_missing_usage_is_not_filled_with_zero(wire, monkeypatch):
    agent = employee(wire)
    conversation = empty_conversation(wire, agent["id"])["id"]
    execute(
        wire,
        monkeypatch,
        ScriptedModel(responses=[response("LONG_" * 700)]),
        submit(wire, conversation, agent, content="保存目标"),
    )
    set_submission_limits(
        wire.app.state.conversation_commands, summary_trigger_tokens=200, summary_keep_tokens=40
    )
    model = ScriptedModel(
        responses=[
            response("摘要").model_copy(update={"usage_metadata": None}),
            response("正式答案"),
        ]
    )
    done = execute(wire, monkeypatch, model, submit(wire, conversation, agent, content="继续"))
    assert done.status == "succeeded" and done.model_calls == 2
    assert done.usage["total_tokens"] is None


def test_database_prevents_two_active_runs_on_one_thread(wire):
    import pytest
    from sqlalchemy.exc import IntegrityError

    agent = employee(wire)
    first_conversation = empty_conversation(wire, agent["id"])["id"]
    second_conversation = empty_conversation(wire, agent["id"])["id"]
    first = submit(wire, first_conversation, agent, content="第一份工作").json()
    second = submit(wire, second_conversation, agent, content="第二份工作").json()
    first_id = first["response"]["id"]
    second_id = second["response"]["id"]
    with pytest.raises(IntegrityError, match="runs.thread_id"):
        with wire.app.state.database.transaction() as db:
            db.get(Run, second_id).thread_id = db.get(Run, first_id).thread_id


def test_failed_summary_is_not_retried_or_published(wire, monkeypatch):
    agent = employee(wire)
    conversation = empty_conversation(wire, agent["id"])["id"]
    execute(
        wire,
        monkeypatch,
        ScriptedModel(responses=[response("LONG_" * 700)]),
        submit(wire, conversation, agent, content="第一问"),
    )
    set_submission_limits(
        wire.app.state.conversation_commands, summary_trigger_tokens=200, summary_keep_tokens=40
    )
    model = ScriptedModel(responses=[response(""), response("不应重试")])
    failed = execute(wire, monkeypatch, model, submit(wire, conversation, agent, content="继续"))
    assert failed.status == "failed" and failed.error_code == "empty_response"
    assert failed.model_calls == 1 and len(model.prompts) == 1
    assert failed.usage["total_tokens"] == 15
