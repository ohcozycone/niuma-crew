"""Live employee authorization and real SDK execution with fake network/model only."""

import json

import httpx
import pytest
from runtime_helpers import bind_model_calls
from test_capability_runtime import ScriptedModel, execute, response, setup, submit

from app.common.errors import ConflictError
from app.runtime.contracts.tools import ToolInvocation
from app.runtime.execution.authorization import authorize_tool
from app.runtime.execution.snapshot_rules import invalidates_memory
from app.runtime.tools.web import WebService
from app.runtime.tools.web_config import WebConfig


def enabled(client):
    _, _, employee, conversation = setup(client)
    employee = client.patch(
        f"/api/agents/{employee['id']}",
        json={
            "expected_revision": employee["revision"],
            "allow_web_access": True,
        },
    ).json()
    client.app.state.runs.configuration.web_ready = True
    return employee, conversation


def revoke(client, employee):
    result = client.patch(
        f"/api/agents/{employee['id']}",
        json={
            "expected_revision": employee["revision"],
            "allow_web_access": False,
        },
    )
    assert result.status_code == 200, result.text


def test_web_snapshot_independent_of_mcp_and_current_server_readiness(api_client):
    employee, conversation = enabled(api_client)
    database = api_client.app.state.database
    config = api_client.app.state.runs.configuration
    with database.transaction() as db:
        snapshot, _ = config.prepare(db, employee["id"], "公开研究", [])
        assert snapshot["allow_web_access"] is True
        assert {b["tool_name"] for b in snapshot["tools"] if b["kind"] == "web"} == {
            "web_search",
            "web_fetch",
        }
        assert not snapshot["tool_catalog"]["sources"]
        assert all("connection_id" not in b for b in snapshot["tools"] if b["kind"] == "web")
        assert "api_key" not in json.dumps(snapshot)
        disabled, _ = config.prepare(db, employee["id"], "普通聊天", [], tools_enabled=False)
        assert disabled["allow_web_access"] is False and not disabled["tools"]
        config.web_ready = False
        not_ready, _ = config.prepare(db, employee["id"], "公开研究", [])
        assert not any(b["kind"] == "web" for b in not_ready["tools"])
        assert "未完成服务器配置" in not_ready["system_prompt"]


def test_real_sdk_runs_both_web_tools_and_persists_provenance(api_client, monkeypatch):
    employee, conversation = enabled(api_client)
    requested = []

    async def dns(host):
        return ["93.184.216.34"]

    def handler(request):
        requested.append(str(request.url))
        if request.url.host == "api.bocha.cn":
            data = {
                "webPages": {
                    "value": [
                        {
                            "name": "Public report",
                            "url": "https://example.com/report",
                            "snippet": "DISCOVERY_SNIPPET",
                        }
                    ]
                }
            }
        else:
            data = {
                "url": "https://example.com/report",
                "content": "PUBLIC_PAGE_CONTENT",
                "title": "Public report",
            }
        return httpx.Response(200, json={"code": 200, "data": data})

    api_client.app.state.run_worker.task_factory.keywords["web"] = WebService(
        WebConfig(bocha_api_key="test-key"),
        transport=httpx.MockTransport(handler),
        resolve=dns,
    )
    model = ScriptedModel(
        responses=[
            response(
                "", [{"name": "web_search", "id": "search", "args": {"query": "public report"}}]
            ),
            response(
                "",
                [
                    {
                        "name": "web_fetch",
                        "id": "fetch",
                        "args": {"url": "https://example.com/report"},
                    }
                ],
            ),
            response("结论 [报告](https://example.com/report)"),
        ]
    )
    run = submit(api_client, conversation).json()["response"]
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "succeeded", result
    assert requested == ["https://api.bocha.cn/v1/web-search", "https://r.jina.ai/"]
    assert "DISCOVERY_SNIPPET" in model.prompts[1]
    assert "PUBLIC_PAGE_CONTENT" in model.prompts[2]
    actions = [step for step in result["steps"] if step["kind"] == "tool_call"]
    assert len(actions) == 2 and all(step["status"] == "succeeded" for step in actions)
    assert all(step["safe_details"]["sources"] for step in actions)
    assert all("search_tools" not in names for names in model.bindings)


def test_revocation_blocks_cached_action_and_invalidates_old_web_memory(api_client):
    employee, conversation = enabled(api_client)
    run = submit(api_client, conversation).json()["response"]
    store = api_client.app.state.run_worker.store
    store.claim(run["id"])
    row, _ = store.load(run["id"])
    invocation = ToolInvocation("tool:search", "web:web_search", "web_search", {"query": "public"})
    (invocation,) = bind_model_calls(store, row.id, invocation)
    permit = store.begin_tool(
        row.id,
        invocation,
        lambda db: api_client.app.state.runs.authorize(row, db=db, invocation=invocation),
    )
    store.finish_action(
        row.id,
        permit.action_key,
        "succeeded",
        result_payload={"content": "cached public evidence", "status": "succeeded", "data": {}},
    )
    revoke(api_client, employee)
    with pytest.raises(ConflictError, match="网页"):
        store.begin_tool(
            row.id,
            invocation,
            lambda db: api_client.app.state.runs.authorize(row, db=db, invocation=invocation),
        )
    with api_client.app.state.database.transaction() as db:
        with pytest.raises(ConflictError):
            authorize_tool(db, row.config_snapshot, invocation)
        after, _ = api_client.app.state.runs.configuration.prepare(
            db, employee["id"], "普通聊天", []
        )
        assert not any(b["kind"] == "web" for b in after["tools"])
        assert invalidates_memory(row.config_snapshot, after)


def test_revocation_before_model_call_makes_no_provider_request(api_client, monkeypatch):
    employee, conversation = enabled(api_client)
    calls = []
    api_client.app.state.run_worker.task_factory.keywords["web"] = WebService(
        WebConfig(bocha_api_key="test-key"),
        transport=httpx.MockTransport(lambda request: calls.append(request)),
    )
    run = submit(api_client, conversation).json()["response"]
    revoke(api_client, employee)
    model = ScriptedModel(
        responses=[response("", [{"name": "web_search", "id": "s", "args": {"query": "public"}}])]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "failed" and result["error"]["code"] == "web_access_revoked"
    assert not calls and not model.prompts


def test_web_only_long_page_has_readable_tail_and_revocation_blocks_reader(api_client, monkeypatch):
    from langchain_core.messages import ToolMessage

    employee, conversation = enabled(api_client)

    async def dns(host):
        return ["93.184.216.34"]

    content = "正文" * 11000 + "WEB_TAIL_MARKER"
    api_client.app.state.run_worker.task_factory.keywords["web"] = WebService(
        WebConfig(bocha_api_key="test-key"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "url": "https://example.com/report",
                        "content": content,
                        "title": "Public report",
                    },
                },
            )
        ),
        resolve=dns,
    )

    class Reader(ScriptedModel):
        result_id: str = ""

        def _generate(self, messages, *args, **kwargs):
            if self._index == 1:
                text = next(m.content for m in reversed(messages) if isinstance(m, ToolMessage))
                hint = next(
                    json.loads(line) for line in text.splitlines() if line.startswith('{"tool":')
                )
                self.result_id = hint["arguments"]["result_id"]
                self.responses[1] = response(
                    "",
                    [
                        {
                            "name": "read_tool_result",
                            "id": "tail",
                            "args": {"result_id": self.result_id, "offset": 22000, "limit": 2000},
                        }
                    ],
                )
            elif self._index == 2:
                text = next(m.content for m in reversed(messages) if isinstance(m, ToolMessage))
                assert "WEB_TAIL_MARKER" in json.loads(text)["text"]
            return super()._generate(messages, *args, **kwargs)

    model = Reader(
        responses=[
            response(
                "",
                [
                    {
                        "name": "web_fetch",
                        "id": "page",
                        "args": {"url": "https://example.com/report"},
                    }
                ],
            ),
            response("placeholder"),
            response("读完公开资料"),
        ]
    )
    accepted = submit(api_client, conversation).json()["response"]
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert model.result_id and all("search_tools" not in names for names in model.bindings)
    revoke(api_client, employee)
    row, _ = api_client.app.state.run_worker.store.load(accepted["id"])
    with api_client.app.state.database.transaction() as db:
        with pytest.raises(ConflictError):
            authorize_tool(
                db,
                row.config_snapshot,
                ToolInvocation(
                    "tool:read-again",
                    "result:web:web_fetch",
                    "read_tool_result",
                    {"result_id": model.result_id},
                ),
            )


def test_revoke_during_length_limited_answer_cannot_publish_web_partial(api_client, monkeypatch):
    from app.resources.employees.models import Agent

    employee, conversation = enabled(api_client)
    api_client.app.state.run_worker.task_factory.keywords["web"] = WebService(
        WebConfig(bocha_api_key="test-key"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "webPages": {
                            "value": [
                                {
                                    "name": "Public report",
                                    "url": "https://example.com/report",
                                    "snippet": "SOURCE",
                                }
                            ]
                        }
                    },
                },
            )
        ),
    )

    class RevokeWhileAnswering(ScriptedModel):
        def _generate(self, messages, *args, **kwargs):
            if self._index == 1:
                with api_client.app.state.database.transaction() as db:
                    db.get(Agent, employee["id"]).allow_web_access = False
            return super()._generate(messages, *args, **kwargs)

    partial = response("WEB_DERIVED_PARTIAL_MUST_NOT_PUBLISH").model_copy(
        update={"response_metadata": {"finish_reason": "length"}}
    )
    model = RevokeWhileAnswering(
        responses=[
            response(
                "", [{"name": "web_search", "id": "search", "args": {"query": "public report"}}]
            ),
            partial,
        ]
    )
    accepted = submit(api_client, conversation).json()["response"]
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "failed", result
    assert not result["content"], result
    row, _ = api_client.app.state.run_worker.store.load(accepted["id"])
    assert not row.result_text


def test_live_database_revocation_during_provider_call_hides_returned_content(
    api_client, monkeypatch
):
    from app.resources.employees.models import Agent

    employee, conversation = enabled(api_client)
    requests = []

    def handler(request):
        requests.append(request)
        with api_client.app.state.database.transaction() as db:
            db.get(Agent, employee["id"]).allow_web_access = False
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "webPages": {
                        "value": [
                            {
                                "name": "Report",
                                "url": "https://example.com/report",
                                "snippet": "REVOKED_PROVIDER_CONTENT",
                            }
                        ]
                    }
                },
            },
        )

    api_client.app.state.run_worker.task_factory.keywords["web"] = WebService(
        WebConfig(bocha_api_key="test-key"), transport=httpx.MockTransport(handler)
    )
    model = ScriptedModel(
        responses=[
            response(
                "", [{"name": "web_search", "id": "search", "args": {"query": "public report"}}]
            ),
            response("must not happen"),
        ]
    )
    accepted = submit(api_client, conversation).json()["response"]
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "failed" and result["error"]["code"] == "web_access_revoked", result
    assert len(requests) == 1 and len(model.prompts) == 1
    assert not result["content"] and "REVOKED_PROVIDER_CONTENT" not in str(result)


def test_web_revocation_keeps_new_non_web_chat_without_raw_inherited_evidence(
    api_client, monkeypatch
):
    from langchain_core.messages import ToolMessage
    from test_runtime_memory import saved_state

    employee, conversation = enabled(api_client)
    api_client.app.state.run_worker.task_factory.keywords["web"] = WebService(
        WebConfig(bocha_api_key="test-key"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "webPages": {
                            "value": [
                                {
                                    "name": "Report",
                                    "url": "https://example.com/report",
                                    "snippet": "RAW_WEB_EVIDENCE_NOT_REUSED",
                                }
                            ]
                        }
                    },
                },
            )
        ),
    )
    first = submit(api_client, conversation).json()["response"]
    model = ScriptedModel(
        responses=[
            response(
                "", [{"name": "web_search", "id": "first", "args": {"query": "public report"}}]
            ),
            response("完成公开检索"),
        ]
    )
    assert execute(api_client, monkeypatch, model, first)["status"] == "succeeded"
    revoke(api_client, employee)
    second = submit(api_client, conversation, content="普通聊天").json()["response"]
    later = ScriptedModel(responses=[response("继续普通聊天")])
    result = execute(api_client, monkeypatch, later, second)
    assert result["status"] == "succeeded", result
    assert all("web_search" not in tools and "web_fetch" not in tools for tools in later.bindings)
    assert all("RAW_WEB_EVIDENCE_NOT_REUSED" not in prompt for prompt in later.prompts)
    assert not any(
        isinstance(m, ToolMessage) and m.tool_call_id == "first"
        for m in saved_state(api_client, second["id"])["messages"]
    )


def test_same_run_checkpoint_resume_rechecks_revoked_web_permission(api_client, monkeypatch):
    import asyncio

    from langchain_core.outputs import ChatGeneration, ChatResult
    from run_helpers import execute_run, read_reply

    employee, conversation = enabled(api_client)
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(200, json={"code": 200, "data": {"webPages": {"value": []}}})

    api_client.app.state.run_worker.task_factory.keywords["web"] = WebService(
        WebConfig(bocha_api_key="test-key"),
        transport=httpx.MockTransport(provider),
    )
    accepted = submit(api_client, conversation).json()["response"]

    async def pause_after_web():
        entered = asyncio.Event()

        class PauseAfterTool(ScriptedModel):
            async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
                if self._index == 0:
                    self._index += 1
                    return ChatResult(
                        generations=[
                            ChatGeneration(
                                message=response(
                                    "",
                                    [
                                        {
                                            "name": "web_search",
                                            "id": "search-before-pause",
                                            "args": {"query": "public report"},
                                        }
                                    ],
                                )
                            )
                        ]
                    )
                entered.set()
                await asyncio.Event().wait()

        monkeypatch.setattr(
            "app.infrastructure.llm.factory.create_chat_model",
            lambda *args, **kwargs: PauseAfterTool(responses=[]),
        )
        task = asyncio.create_task(execute_run(api_client, accepted["id"]))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(pause_after_web())
    row, _ = api_client.app.state.run_worker.store.load(accepted["id"])
    assert row.status == "running" and row.checkpoint_id and row.tool_calls == 1
    revoke(api_client, employee)
    assert api_client.app.state.run_worker.store.recover(resume=True) == []
    later = ScriptedModel(responses=[response("must not resume revoked evidence")])
    monkeypatch.setattr(
        "app.infrastructure.llm.factory.create_chat_model", lambda *args, **kwargs: later
    )
    asyncio.run(execute_run(api_client, accepted["id"]))
    api_client.app.state.conversation_acceptance.sweep()
    result = read_reply(api_client, accepted["id"])
    assert result["status"] == "failed" and result["error"]["code"] == "web_access_revoked"
    assert len(calls) == 1 and not later.prompts and not result["content"]
