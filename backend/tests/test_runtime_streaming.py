import asyncio
import threading
import time

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from pydantic import Field
from run_helpers import active_step, latest_model, load_run, read_reply, reply_path
from test_capability_runtime import ScriptedModel, execute, response, setup, submit
from test_conversations import live_client as live_client
from test_conversations import wait_run

from app.runtime.agent.streaming import ContentUpdate, RunProgress


class StreamingModel(ScriptedModel):
    path: str
    gates: list = Field(default_factory=lambda: [threading.Event(), threading.Event()])
    cleaned: bool = False

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        round_number = self._index
        self._index += 1
        try:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[{"type": "reasoning", "reasoning": f"第{round_number + 1}轮摘要"}]
                )
            )
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="先读取技能" if round_number == 0 else "回答")
            )
            while not self.gates[round_number].is_set():
                await asyncio.sleep(0.005)
            if round_number == 0:
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        tool_call_chunks=[
                            {
                                "name": "read_file",
                                "args": '{"file_path":"' + self.path + '"}',
                                "id": "read-1",
                                "index": 0,
                            }
                        ],
                        response_metadata={"finish_reason": "tool_calls"},
                        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                    )
                )
            else:
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="完成",
                        response_metadata={"finish_reason": "stop"},
                        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                    )
                )
        finally:
            self.cleaned = True


def test_real_stream_flushes_while_idle_and_separates_tool_rounds(live_client, monkeypatch):
    skill, _, _, conversation = setup(live_client)
    model = StreamingModel(responses=[], path=f"/skills/s-{skill['id']}/SKILL.md")
    monkeypatch.setattr("app.infrastructure.llm.factory.create_chat_model", lambda *a, **k: model)
    decrypt = live_client.app.state.model_connections.vault.decrypt
    decryptions = []

    def count(value):
        decryptions.append(True)
        return decrypt(value)

    monkeypatch.setattr(live_client.app.state.model_connections.vault, "decrypt", count)
    run = submit(live_client, conversation).json()["response"]
    try:
        partial = wait_run(
            live_client,
            run["id"],
            lambda r: bool(latest_model(r) and latest_model(r)["output_text"] == "先读取技能"),
        )
        assert partial["status"] == "running" and partial["content"] == "先读取技能"
        assert latest_model(partial)["reasoning_text"] == "第1轮摘要"
        assert len(partial["steps"]) == 1
        assert active_step(partial)["kind"] == "model_call"
        model.gates[0].set()
        second = wait_run(
            live_client,
            run["id"],
            lambda r: bool(latest_model(r) and latest_model(r)["output_text"] == "回答"),
        )
        assert latest_model(second)["id"] != latest_model(partial)["id"]
        steps = read_reply(live_client, run["id"])["steps"]
        assert [s["kind"] for s in steps] == [
            "model_call",
            "tool_call",
            "skill_activation",
            "model_call",
        ]
        assert steps[0]["safe_details"]["has_tool_calls"]
        assert len(second["steps"]) == 4
        assert "BODY_MARKER_P1" not in str(second)
        # 新查询须独立于流恢复当前完整草稿。
        assert latest_model(read_reply(live_client, run["id"])) == latest_model(second)
        model.gates[1].set()
        completed = wait_run(live_client, run["id"])
        assert completed["content"] == "回答完成" and latest_model(completed) is None
        assert active_step(completed) is None and len(completed["steps"]) == 4
        assert completed["usage"]["total_tokens"] == 30 and len(decryptions) == 1
    finally:
        for gate in model.gates:
            gate.set()


def test_sdk_cancel_retains_draft_as_process_and_closes_upstream(live_client, monkeypatch):
    skill, _, _, conversation = setup(live_client)
    model = StreamingModel(responses=[], path=f"/skills/s-{skill['id']}/SKILL.md")
    monkeypatch.setattr("app.infrastructure.llm.factory.create_chat_model", lambda *a, **k: model)
    run = submit(live_client, conversation).json()["response"]
    wait_run(
        live_client,
        run["id"],
        lambda r: bool(latest_model(r) and latest_model(r)["output_text"]),
    )
    live_client.post(reply_path(live_client, run["id"]) + "/stop", json={})
    completed = wait_run(live_client, run["id"])
    assert completed["status"] == "cancelled" and completed["content"] == ""
    assert model.cleaned and model._index == 1
    step = read_reply(live_client, run["id"])["steps"][0]
    assert step["output_text"] == "先读取技能" and step["reasoning_text"] == "第1轮摘要"
    assert step["status"] == "unknown" and completed["usage"]["total_tokens"] is None


def test_complete_step_rejects_late_content_and_content_does_not_reload_steps(api_client):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    store.claim(run["id"])
    store.start_action(run["id"], "model:1", "model_call")
    before = read_reply(api_client, run["id"])
    before_actions = load_run(api_client, run["id"]).actions_revision
    old = ContentUpdate("model:1", "草稿", "摘要", False, False)
    store.update_progress(run["id"], [old])
    middle = read_reply(api_client, run["id"])
    assert (
        middle["version"] > before["version"]
        and load_run(api_client, run["id"]).actions_revision == before_actions
    )
    store.finish_action(
        run["id"],
        "model:1",
        content=ContentUpdate("model:1", "完整回答", "完整摘要", False, False),
    )
    complete = read_reply(api_client, run["id"])
    store.update_progress(run["id"], [old])
    assert read_reply(api_client, run["id"]) == complete


def test_reasoning_budget_is_utf8_safe_and_final_reconciliation_is_not_append():
    progress = RunProgress(30, 9)
    progress.record(
        "model:1",
        AIMessage(
            content=[
                {"type": "reasoning", "reasoning": "一二三四"},
                {"type": "text", "text": '{"ok":true}'},
            ]
        ),
    )
    final = progress.record(
        "model:1",
        AIMessage(
            content=[
                {"type": "reasoning", "reasoning": "一二三四"},
                {"type": "text", "text": '{"ok":true}'},
            ]
        ),
        complete=True,
    )
    assert final.reasoning_text == "一二三" and final.reasoning_truncated
    assert final.output_text == '{"ok":true}'
    second = progress.record(
        "model:2", AIMessage(content=[{"type": "reasoning", "reasoning": "另一次"}])
    )
    assert second.reasoning_text == "" and second.reasoning_truncated
    progress.bind("model:1", {"langgraph_node": "model", "langgraph_step": 1})
    progress.feed(AIMessageChunk(content="迟到"), {"langgraph_node": "model", "langgraph_step": 1})
    assert progress.contents["model:1"] == final


@pytest.mark.parametrize("reason", ["length", "auth", "bad_request"])
def test_model_and_run_errors_match_and_partial_answer_is_real(api_client, monkeypatch, reason):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    if reason == "length":
        model = ScriptedModel(
            responses=[
                response("部分回答").model_copy(
                    update={"response_metadata": {"finish_reason": "length"}}
                )
            ]
        )
        code = "output_limit_exceeded"
    else:

        class AuthFailure(ScriptedModel):
            def _generate(self, *args, **kwargs):
                cls, status, body = (
                    (openai.AuthenticationError, 401, {})
                    if reason == "auth"
                    else (openai.BadRequestError, 400, {"code": "context_length_exceeded"})
                )
                raise cls(
                    "hidden-secret",
                    response=httpx.Response(
                        status, request=httpx.Request("POST", "https://example.test")
                    ),
                    body=body,
                )

        model = AuthFailure(responses=[])
        code = "upstream_auth_failed" if reason == "auth" else "context_limit_exceeded"
    result = execute(api_client, monkeypatch, model, run)
    step = read_reply(api_client, run["id"])["steps"][0]
    assert result["status"] == "failed" and result["error"]["code"] == step["error_code"] == code
    assert result["content"] == ("部分回答" if reason == "length" else "")
    assert "hidden-secret" not in str(result) + str(step)


def test_scanner_crash_closes_admission_and_readiness(live_client, monkeypatch):
    def fail():
        raise ValueError("hidden-secret")

    monkeypatch.setattr(live_client.app.state.run_worker.store, "queued_metadata", fail)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and live_client.get("/ready").status_code != 503:
        time.sleep(0.01)
    assert live_client.get("/ready").json()["status"] == "failed"
    _, _, _, conversation = setup(live_client)
    assert submit(live_client, conversation).status_code == 503
    assert live_client.get("/health").status_code == 200


def test_live_configuration_revocation_is_failed_not_cancelled(live_client, monkeypatch):
    skill, connection, _, conversation = setup(live_client)
    model = StreamingModel(responses=[], path=f"/skills/s-{skill['id']}/SKILL.md")
    monkeypatch.setattr("app.infrastructure.llm.factory.create_chat_model", lambda *a, **k: model)
    run = submit(live_client, conversation).json()["response"]
    wait_run(
        live_client,
        run["id"],
        lambda r: bool(latest_model(r) and latest_model(r)["output_text"]),
    )
    from configuration_helpers import patch_current

    patch_current(
        live_client, f"/api/model-connections/{connection['id']}", json={"model_id": "changed"}
    )
    result = wait_run(live_client, run["id"])
    assert result["status"] == "failed" and result["error"]["code"] == "model_configuration_changed"
    assert model.cleaned


def test_truncated_tool_request_is_not_promoted_to_partial_answer(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="先读取技能",
                invalid_tool_calls=[
                    {"name": "read_file", "args": "{", "id": "broken", "error": "incomplete"}
                ],
                response_metadata={"finish_reason": "length"},
            )
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["error"]["code"] == "output_limit_exceeded"
    assert result["content"] == ""
    assert "已保留部分回答" not in result["error"]["message"]


def test_extension_reasoning_reaches_progress_evidence_and_checkpoint_without_provider_branch(
    api_client, monkeypatch
):
    import json

    from run_helpers import checkpoint_store, execute_run

    from app.runtime.agent.checkpoints import checkpoint_config
    from app.runtime.execution.models import Run, RunAction

    requests = []

    def handle(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert "legacy_request_format" not in payload
        pieces = [
            {"delta": {"role": "assistant", "reasoning_content": "先核对"}},
            {"delta": {"reasoning_content": "再回答"}},
            {"delta": {"content": "合成答复"}},
            {"delta": {}, "finish_reason": "stop"},
        ]
        events = [
            {
                "id": "fixture-reasoning",
                "object": "chat.completion.chunk",
                "model": "fixture",
                "created": 1,
                "choices": [{"index": 0, "finish_reason": None, **piece}],
            }
            for piece in pieces
        ]
        events.append(
            {
                "id": "fixture-reasoning",
                "object": "chat.completion.chunk",
                "model": "fixture",
                "created": 1,
                "choices": [],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text="".join("data: " + json.dumps(event) + "\n\n" for event in events)
            + "data: [DONE]\n\n",
        )

    class OfflineClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handle)
            super().__init__(**kwargs)

    monkeypatch.setattr("app.infrastructure.llm.factory.httpx.AsyncClient", OfflineClient)
    _, _, _, conversation = setup(api_client)
    accepted = submit(api_client, conversation).json()["response"]
    asyncio.run(execute_run(api_client, accepted["id"]))
    api_client.app.state.conversation_acceptance.sweep()
    result = read_reply(api_client, accepted["id"])
    assert result["status"] == "succeeded" and result["content"] == "合成答复"
    step = next(item for item in result["steps"] if item["kind"] == "model_call")
    assert step["reasoning_text"] == "先核对再回答" and not step["reasoning_truncated"]
    assert len(requests) == 1
    with api_client.app.state.database.transaction() as db:
        run = db.get(Run, accepted["id"])
        action = db.get(RunAction, step["id"])
        evidence = json.loads(api_client.app.state.files.read(action.response_file_id))
        assert evidence["payload"]["reasoning_content"] == "先核对再回答"
        config = checkpoint_config(run.thread_id, run.checkpoint_id)
    with checkpoint_store(api_client).reader() as saver:
        saved = saver.get_tuple(config).checkpoint["channel_values"]["messages"]
    assert any(
        isinstance(message, AIMessage)
        and message.additional_kwargs.get("reasoning_content") == "先核对再回答"
        for message in saved
    )


@pytest.mark.parametrize("content", ["", "  \n", [{"type": "reasoning", "reasoning": "过程摘要"}]])
def test_empty_final_response_fails_model_action_and_keeps_usage(api_client, monkeypatch, content):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    model = ScriptedModel(
        responses=[
            AIMessage(
                content=content,
                response_metadata={"finish_reason": "stop"},
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            )
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    step = read_reply(api_client, run["id"])["steps"][0]
    assert result["status"] == "failed" and result["error"]["code"] == "empty_response"
    assert step["status"] == "failed" and step["error_code"] == "empty_response"
    assert result["usage"]["total_tokens"] == 15 and model._index == 1


def test_empty_text_with_valid_tool_call_still_executes(api_client, monkeypatch):
    skill, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": "read_file",
                        "id": "read",
                        "args": {"file_path": f"/skills/s-{skill['id']}/SKILL.md"},
                    }
                ],
            ),
            response("读取完成"),
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "succeeded" and result["content"] == "读取完成"
    assert len(model.prompts) == 2 and "BODY_MARKER_P1" in model.prompts[-1]
