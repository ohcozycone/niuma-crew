"""Offline wire probe: synthetic Context7-shaped catalog, real platform+LC+OpenAI SDK."""

import asyncio
import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from test_agent_foundations import run_id
from test_capability_runtime import setup

from app.llm.factory import create_chat_model
from app.tools.contracts import digest, exposed_name

OUTPUT = Path(
    os.environ.get(
        "NIUMA_MCP_AUDIT_OUTPUT",
        str(Path(tempfile.gettempdir()) / "niuma-mcp-review-20261030-recheck"),
    )
)
OUTPUT.mkdir(parents=True, exist_ok=True)


class Context7Fixture:
    calls = []
    fail_docs = False
    catalog = [
        {
            "name": "resolve-library-id",
            "description": "Resolve a library name to a Context7 library ID before query-docs.",
            "input_schema": {
                "type": "object",
                "properties": {"libraryName": {"type": "string"}, "query": {"type": "string"}},
                "required": ["libraryName", "query"],
            },
            "descriptor_hash": digest("resolve-v1"),
            "recovery": "never",
        },
        {
            "name": "query-docs",
            "description": "Retrieve up-to-date documentation and code examples for a library.",
            "input_schema": {
                "type": "object",
                "properties": {"libraryId": {"type": "string"}, "query": {"type": "string"}},
                "required": ["libraryId", "query"],
            },
            "descriptor_hash": digest("query-v1"),
            "recovery": "never",
        },
    ]

    def __init__(self, *args):
        pass

    async def discover(self):
        return self.catalog

    async def invoke(self, name, arguments, expected_hash, guard):
        await guard()
        self.calls.append({"name": name, "arguments": arguments})
        if self.fail_docs and name == "query-docs":
            return (
                [
                    {
                        "type": "text",
                        "text": "Context7 fixture error: query failed; no documentation obtained.",
                    }
                ],
                {},
                "error",
            )
        text = (
            "Library ID: /langchain-ai/langchain; Title: LangChain"
            if name == "resolve-library-id"
            else "FIXTURE latest LangChain documentation: feature A. This is synthetic probe evidence."
        )
        return ([{"type": "text", "text": text}], {}, "success")


def grant_context7(client, agent):
    client.app.state.tools.client_factory = Context7Fixture
    created = client.post(
        "/api/tool-connections",
        json={
            "name": "Context7 fixture",
            "kind": "mcp_http",
            "auth_type": "none",
            "public_config": {"url": "https://mcp.tavily.com/mcp"},
        },
    )
    assert created.status_code == 201, created.text
    connection = created.json()
    candidate = client.post(f"/api/tool-connections/{connection['id']}/discover").json()
    approved = client.post(
        f"/api/tool-connections/{connection['id']}/approve",
        json={
            "expected_config_revision": candidate["config_revision"],
            "expected_catalog_revision": candidate["catalog_revision"],
            "candidate_hash": candidate["discovery_candidate"]["hash"],
        },
    )
    assert approved.status_code == 200, approved.text
    catalog = approved.json()["approved_catalog"]
    assigned = client.put(
        f"/api/agents/{agent['id']}/tool-grants",
        json={
            "expected_revision": agent["revision"],
            "grants": [
                {
                    "connection_id": connection["id"],
                    "tools": [x["name"] for x in catalog],
                    "expected_descriptors": {x["name"]: x["descriptor_hash"] for x in catalog},
                    "scope_policy": {"mode": "provider", "max_calls": 5},
                }
            ],
        },
    )
    assert assigned.status_code == 200, assigned.text
    return connection


def sse(deltas, reason):
    chunks = [
        {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]} for delta in deltas
    ]
    chunks.append(
        {
            "choices": [{"index": 0, "delta": {}, "finish_reason": reason}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    )
    payload = (
        "".join(
            "data: "
            + json.dumps({"id": "fixture", "object": "chat.completion.chunk", **chunk})
            + "\n\n"
            for chunk in chunks
        )
        + "data: [DONE]\n\n"
    )
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=payload)


def tool_delta(name, args, ident, index=0):
    encoded = json.dumps(args)
    middle = len(encoded) // 2
    return [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "index": index,
                    "id": ident,
                    "type": "function",
                    "function": {"name": name, "arguments": encoded[:middle]},
                }
            ],
        },
        {"tool_calls": [{"index": index, "function": {"arguments": encoded[middle:]}}]},
    ]


@pytest.mark.parametrize(
    "mode", ["direct", "explicit_direct", "sequential", "parallel", "error_then_claim"]
)
def test_context7_wire(api_client, monkeypatch, mode):
    _, _, agent, conversation = setup(api_client)
    connection = grant_context7(api_client, agent)
    Context7Fixture.calls = []
    Context7Fixture.fail_docs = mode == "error_then_claim"
    names = {
        item["name"]: exposed_name(connection["id"], item["name"])
        for item in Context7Fixture.catalog
    }
    requests = []
    resolve_args = {"libraryName": "LangChain", "query": "最新版本文档有什么新功能"}
    docs_args = {"libraryId": "/langchain-ai/langchain", "query": "最新版本文档有什么新功能"}

    def upstream(request):
        body = json.loads(request.content)
        requests.append(body)
        if mode in ("direct", "explicit_direct"):
            return sse(
                [{"role": "assistant", "content": "LangChain 最新版新增了虚构功能。"}], "stop"
            )
        if len(requests) == 1:
            deltas = [{"role": "assistant", "reasoning_content": "I need Context7 documentation."}]
            deltas += tool_delta(names["resolve-library-id"], resolve_args, "resolve")
            if mode == "parallel":
                deltas += tool_delta(names["query-docs"], docs_args, "docs", 1)
            return sse(deltas, "tool_calls")
        if len(requests) == 2 and mode in ("sequential", "error_then_claim"):
            return sse(tool_delta(names["query-docs"], docs_args, "docs"), "tool_calls")
        if mode == "error_then_claim":
            return sse(
                [
                    {
                        "role": "assistant",
                        "content": "我已经成功查询并阅读 Context7 的 LangChain 最新官方文档，新增功能 A。",
                    }
                ],
                "stop",
            )
        return sse(
            [{"role": "assistant", "content": "根据 Context7 返回的测试文档，新增功能 A。"}], "stop"
        )

    @asynccontextmanager
    async def session(config, *, max_tokens):
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as transport:
            yield create_chat_model(config, transport=transport, max_tokens=max_tokens)

    monkeypatch.setattr("app.agent_runtime.langchain.model_session", session)
    content = (
        "必须使用 Context7 查询 LangChain 最新文档再回答；禁止凭记忆回答。"
        if mode == "explicit_direct"
        else "请查看 LangChain 最新版本的文档有什么新功能。"
    )
    accepted = api_client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": content, "client_request_id": str(uuid4())},
    )
    assert accepted.status_code == 202, accepted.text
    ident = run_id(api_client, accepted.json())
    asyncio.run(api_client.app.state.runner.coordinator.run(ident))
    completed = api_client.get(f"/api/runs/{ident}").json()
    assert completed["status"] == "succeeded", completed
    for request in requests:
        tools = {t["function"]["name"]: t["function"] for t in request["tools"]}
        for item in Context7Fixture.catalog:
            assert tools[names[item["name"]]]["description"] == item["description"]
            assert tools[names[item["name"]]]["parameters"] == item["input_schema"]
        assert "tool_choice" not in request
        assert "parallel_tool_calls" not in request
        assert request["stream"] is True
        assert request["stream_options"] == {"include_usage": True}
    assert len(Context7Fixture.calls) == (0 if mode in ("direct", "explicit_direct") else 2)
    assert (
        len(requests)
        == {
            "direct": 1,
            "explicit_direct": 1,
            "sequential": 3,
            "parallel": 2,
            "error_then_claim": 3,
        }[mode]
    )
    if mode not in ("direct", "explicit_direct"):
        final = requests[-1]["messages"]
        call_ids = [c["id"] for m in final for c in m.get("tool_calls", [])]
        result_ids = [m["tool_call_id"] for m in final if m["role"] == "tool"]
        assert set(call_ids) == set(result_ids) == {"resolve", "docs"}
        assert not any("reasoning_content" in m for m in final)
    if mode == "explicit_direct":
        assert any("必须使用 Context7" in str(m["content"]) for m in requests[0]["messages"])
    if mode == "error_then_claim":
        assert any(s["kind"] == "tool_call" and s["status"] == "failed" for s in completed["steps"])
        assert any(
            m["role"] == "tool" and "query failed" in str(m["content"])
            for m in requests[-1]["messages"]
        )
    summary = {
        "mode": mode,
        "status": completed["status"],
        "model_requests": len(requests),
        "mcp_calls": Context7Fixture.calls,
        "request_keys": list(requests[0]),
        "tool_names": list(names),
        "assistant_content": completed.get("assistant_content"),
        "tool_steps": sum(s["kind"] == "tool_call" for s in completed["steps"]),
        "failed_tool_steps": sum(
            s["kind"] == "tool_call" and s["status"] == "failed" for s in completed["steps"]
        ),
        "reasoning_content_roundtrip": False,
    }
    (OUTPUT / f"wire-{mode}.json").write_text(
        json.dumps({"summary": summary, "requests": requests}, ensure_ascii=False, indent=2)
    )
    print(json.dumps(summary, ensure_ascii=False))
