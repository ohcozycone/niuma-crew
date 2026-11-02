"""Actual SDK streams, durable progress and failure boundaries; no external model calls."""

import asyncio
import threading
import time

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from pydantic import Field
from test_capability_runtime import ScriptedModel, execute, response, setup, submit
from test_conversations import live_client as live_client
from test_conversations import wait_run

from app.agent_runtime.streaming import ContentUpdate, RunProgress


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
    monkeypatch.setattr("app.llm.factory.create_chat_model", lambda *a, **k: model)
    decrypt = live_client.app.state.model_connections.vault.decrypt
    decryptions = []

    def count(value):
        decryptions.append(True)
        return decrypt(value)

    monkeypatch.setattr(live_client.app.state.model_connections.vault, "decrypt", count)
    run = submit(live_client, conversation).json()
    try:
        partial = wait_run(
            live_client,
            run["id"],
            lambda r: bool(
                r["current_model"] and r["current_model"]["output_text"] == "先读取技能"
            ),
        )
        assert partial["status"] == "running" and partial["assistant_content"] == ""
        assert partial["current_model"]["reasoning_text"] == "第1轮摘要"
        assert partial["action_count"] == 1
        assert partial["current_activity"]["kind"] == "model_call"
        model.gates[0].set()
        second = wait_run(
            live_client,
            run["id"],
            lambda r: bool(r["current_model"] and r["current_model"]["output_text"] == "回答"),
        )
        assert second["current_model"]["action_id"] != partial["current_model"]["action_id"]
        steps = live_client.get(f"/api/runs/{run['id']}/actions").json()["items"]
        assert [s["kind"] for s in steps] == [
            "model_call",
            "tool_call",
            "skill_activation",
            "model_call",
        ]
        assert steps[0]["safe_details"]["has_tool_calls"]
        assert second["action_count"] == 4
        assert "BODY_MARKER_P1" not in str(second)
        # A newly fetched snapshot restores the exact current draft, independently of the stream.
        assert (
            live_client.get(f"/api/runs/{run['id']}").json()["current_model"]
            == second["current_model"]
        )
        model.gates[1].set()
        completed = wait_run(live_client, run["id"])
        assert completed["assistant_content"] == "回答完成" and completed["current_model"] is None
        assert completed["current_activity"] is None and completed["action_count"] == 4
        assert completed["usage"]["total_tokens"] == 30 and len(decryptions) == 1
    finally:
        for gate in model.gates:
            gate.set()


def test_sdk_cancel_retains_draft_as_process_and_closes_upstream(live_client, monkeypatch):
    skill, _, _, conversation = setup(live_client)
    model = StreamingModel(responses=[], path=f"/skills/s-{skill['id']}/SKILL.md")
    monkeypatch.setattr("app.llm.factory.create_chat_model", lambda *a, **k: model)
    run = submit(live_client, conversation).json()
    wait_run(
        live_client,
        run["id"],
        lambda r: bool(r["current_model"] and r["current_model"]["output_text"]),
    )
    live_client.post(f"/api/runs/{run['id']}/cancel", json={})
    completed = wait_run(live_client, run["id"])
    assert completed["status"] == "cancelled" and completed["assistant_content"] == ""
    assert model.cleaned and model._index == 1
    step = live_client.get(f"/api/runs/{run['id']}/actions").json()["items"][0]
    assert step["output_text"] == "先读取技能" and step["reasoning_text"] == "第1轮摘要"
    assert step["status"] == "unknown" and completed["usage"]["total_tokens"] is None


def test_complete_step_rejects_late_content_and_content_does_not_reload_steps(api_client):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation).json()
    store = api_client.app.state.runner.store
    store.claim(run["id"])
    store.start_action(run["id"], "model:1", "model_call")
    before = api_client.get(f"/api/runs/{run['id']}").json()
    old = ContentUpdate("model:1", "草稿", "摘要", False, False)
    store.update_progress(run["id"], [old])
    middle = api_client.get(f"/api/runs/{run['id']}").json()
    assert (
        middle["revision"] > before["revision"]
        and middle["actions_revision"] == before["actions_revision"]
    )
    store.finish_action(
        run["id"], "model:1", content=ContentUpdate("model:1", "完整回答", "完整摘要", False, False)
    )
    complete = api_client.get(f"/api/runs/{run['id']}").json()
    store.update_progress(run["id"], [old])
    assert api_client.get(f"/api/runs/{run['id']}").json() == complete


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
    run = submit(api_client, conversation).json()
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
    step = api_client.get(f"/api/runs/{run['id']}/actions").json()["items"][0]
    assert result["status"] == "failed" and result["error"]["code"] == step["error_code"] == code
    assert result["assistant_content"] == ("部分回答" if reason == "length" else "")
    assert "hidden-secret" not in str(result) + str(step)


def test_scanner_crash_closes_admission_and_readiness(live_client, monkeypatch):
    def fail():
        raise ValueError("hidden-secret")

    monkeypatch.setattr(live_client.app.state.runner.store, "queued_metadata", fail)
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
    monkeypatch.setattr("app.llm.factory.create_chat_model", lambda *a, **k: model)
    run = submit(live_client, conversation).json()
    wait_run(
        live_client,
        run["id"],
        lambda r: bool(r["current_model"] and r["current_model"]["output_text"]),
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
    run = submit(api_client, conversation).json()
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
    assert result["assistant_content"] == ""
    assert "已保留部分回答" not in result["error"]["message"]
