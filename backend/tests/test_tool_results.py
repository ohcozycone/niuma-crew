"""Result cursors retain source grants; final prose cannot replace retrieval evidence."""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage
from test_capability_runtime import ScriptedModel, execute, response, setup, submit
from test_tool_readers import search_setup

from app.execution.contracts import RuntimeFailure
from app.execution.runtime.tool_calls import read_observations
from app.execution.runtime.tool_results import ToolResults, _requested_web_reads, _result_text
from app.mcp.contracts import exposed_name


def result_fixture(text="extracted text"):
    data = {"structured": {"results": [{"url": "https://example.com/docs", "raw_content": text}]}}
    envelope = {
        "platform_result": {"binding_id": "grant", "extracted_urls": ["https://example.com/docs"]},
        "data": data,
    }
    encoded = json.dumps(envelope, ensure_ascii=False).encode()
    resource = SimpleNamespace(
        list_sources=lambda: [{"id": "result", "name": "tool-result-call.json"}],
        read_file=lambda key: encoded,
    )
    results = ToolResults({"tools": [{"binding_id": "grant", "kind": "mcp_http"}]}, resource)
    return results, len(_result_text(data))


def test_result_reader_rejects_cross_run_or_arbitrary_file_ids():
    results, _ = result_fixture()
    with pytest.raises(RuntimeFailure, match="tool_not_allowed"):
        results.load("other-run")
    page = json.loads(results.read_page("result", offset=4, limit=20))
    assert page["offset"] == 4 and page["end"] == 24
    assert page["next_offset"] == 24
    with pytest.raises(RuntimeFailure, match="tool_arguments_invalid"):
        results.read_page("result", limit=12001)


def test_evidence_rejects_zero_calls_wrong_target_and_gaps():
    results, size = result_fixture()
    target = "读取 https://example.com/docs"
    with pytest.raises(RuntimeFailure, match="external_read_unverified"):
        results.verify_web_reads(target, [])
    partial = ToolMessage(
        content=json.dumps({"result_id": "result", "preview_end": 20}),
        tool_call_id="call",
        name="mcp_x",
    )
    tail = ToolMessage(
        content=json.dumps({"result_id": "result", "offset": 21, "end": size}),
        tool_call_id="read",
        name="read_tool_result",
    )
    with pytest.raises(RuntimeFailure, match="external_read_unverified"):
        results.verify_web_reads(target, read_observations([partial, tail]))
    tail.content = json.dumps({"result_id": "result", "offset": 20, "end": size})
    results.verify_web_reads(target, read_observations([partial, tail]))
    with pytest.raises(RuntimeFailure, match="external_read_unverified"):
        results.verify_web_reads(
            "读取 https://example.com/another", read_observations([partial, tail])
        )
    assert not _requested_web_reads("https://example.com/docs 这个 URL 的格式是什么？")
    assert not _requested_web_reads("读取附件，内容含URL https://example.com/docs")
    old = ToolMessage(
        content=json.dumps({"result_id": "previous-run", "preview_end": 999}),
        tool_call_id="old",
        name="mcp_old",
    )
    results.verify_web_reads(target, read_observations([old, partial, tail]))


def test_real_loop_does_not_publish_hallucinated_page_read(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation, content="读下 https://example.com/docs 页面内容").json()[
        "response"
    ]
    model = ScriptedModel(responses=[response("已成功读取该页面，它介绍了虚构的功能。")])
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "failed", result
    assert result["error"]["code"] == "external_read_unverified"
    assert not result["content"]


def test_real_loop_pages_result_without_host_file_grant(api_client, monkeypatch):
    _, conversation, connection = search_setup(api_client)
    run = submit(api_client, conversation).json()["response"]

    class Pager(ScriptedModel):
        def _generate(self, *args, **kwargs):
            if self._index == 1:
                file = next(
                    ref
                    for ref in api_client.app.state.files.sources(run["id"])
                    if ref["name"].startswith("tool-result-")
                )
                self.responses[1] = response(
                    "",
                    [
                        {
                            "name": "read_tool_result",
                            "id": "page",
                            "args": {"result_id": file["id"], "offset": 3000, "limit": 1000},
                        }
                    ],
                )
            return super()._generate(*args, **kwargs)

    model = Pager(
        responses=[
            response(
                "",
                [
                    {
                        "name": exposed_name(connection["id"], "tavily_search"),
                        "id": "search",
                        "args": {"query": "web"},
                    }
                ],
            ),
            response(),
            response("已阅读返回的摘要片段，未声称全文。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "succeeded", result
    assert all("read_file" not in tools and "read_tool_result" in tools for tools in model.bindings)
    assert '"offset": 3000' in model.prompts[-1]
    assert [
        item["safe_details"].get("model_tool")
        for item in result["steps"]
        if item["kind"] == "tool_call"
    ] == [exposed_name(connection["id"], "tavily_search"), "read_tool_result"]


def test_successful_target_extraction_is_verified_but_not_labelled_full_text(
    api_client, monkeypatch
):
    from test_agent_foundations import SearchClient

    _, conversation, connection = search_setup(api_client)

    async def extract(self, name, arguments, expected_hash, guard):
        await guard()
        return (
            [],
            {
                "structured_content": {
                    "results": [
                        {"url": "https://example.com/docs", "raw_content": "fixture extracted text"}
                    ]
                }
            },
            "success",
        )

    monkeypatch.setattr(SearchClient, "invoke", extract)
    run = submit(api_client, conversation, content="读取 https://example.com/docs").json()[
        "response"
    ]
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": exposed_name(connection["id"], "tavily_search"),
                        "id": "retrieve",
                        "args": {"query": "target"},
                    }
                ],
            ),
            response("根据取得的提取文本回答。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "succeeded", result
    source = next(
        item["safe_details"]["sources"][0]
        for item in result["steps"]
        if item["kind"] == "tool_call"
    )
    assert source["text_obtained"] and not source["full_text"]


def test_result_reader_rechecks_originating_permission(api_client):

    from sqlalchemy import select

    from app.employees.access import authorize_tool
    from app.employees.models import AgentToolGrant
    from app.errors import ConflictError
    from app.execution.contracts import ToolInvocation
    from app.execution.models import Run

    agent, conversation, _ = search_setup(api_client)
    run = submit(api_client, conversation).json()["response"]
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, run["id"])
        binding = row.config_snapshot["tools"][0]
        invocation = ToolInvocation(
            "tool:page",
            "result:" + binding["binding_id"],
            "read_tool_result",
            {"result_id": "fixture"},
        )
        assert authorize_tool(db, row.config_snapshot, invocation)["recovery"] == "readonly"
        grant = db.scalar(select(AgentToolGrant).where(AgentToolGrant.agent_id == agent["id"]))
        grant.enabled = False
        db.flush()
        with pytest.raises(ConflictError, match="员工工具许可已改变"):
            authorize_tool(db, row.config_snapshot, invocation)
