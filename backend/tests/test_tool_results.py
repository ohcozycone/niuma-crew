import json
from types import SimpleNamespace

import pytest
from test_capability_runtime import ScriptedModel, execute, response, setup, submit
from test_tool_discovery import discovery_response
from test_tool_readers import search_setup

from app.agent.errors import RuntimeFailure
from app.execution.tool_results import ToolResults, _legacy_result_text
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
    return results, len(_legacy_result_text(data))


def test_result_reader_rejects_cross_run_or_arbitrary_file_ids():
    results, _ = result_fixture()
    with pytest.raises(RuntimeFailure, match="tool_not_allowed"):
        results.load("other-run")
    page = json.loads(results.read_page("result", offset=4, limit=20))
    assert page["offset"] == 4 and page["end"] == 24
    assert page["next_offset"] == 24
    assert json.loads(results.read_page("result", limit=15000))["next_offset"] is None


@pytest.mark.parametrize("limit", [1, 6000, 12000, 15000, 1000000000])
def test_reader_treats_limit_as_requested_size_and_preserves_utf8_cursor(limit):
    results, total = result_fixture("正文" * (8 if limit == 1 else 20000))
    offset, chunks = 0, []
    while True:
        page = json.loads(results.read_page("result", offset=offset, limit=limit))
        assert len(page["text"]) <= limit and len(page["text"].encode()) <= 8000
        assert page["end"] == offset + len(page["text"])
        chunks.append(page["text"])
        if page["next_offset"] is None:
            assert page["end"] == total
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert "".join(chunks) == _legacy_result_text(results.load("result")["data"])


def test_generic_loop_does_not_classify_web_intent(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    run = submit(api_client, conversation, content="读下 https://example.com/docs 页面内容").json()[
        "response"
    ]
    model = ScriptedModel(responses=[response("已成功读取该页面，它介绍了虚构的功能。")])
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "succeeded", result


def test_real_loop_pages_result_without_host_file_grant(api_client, monkeypatch):
    _, conversation, connection = search_setup(api_client)
    run = submit(api_client, conversation).json()["response"]

    class Pager(ScriptedModel):
        def _generate(self, *args, **kwargs):
            if self._index == 2:
                file = next(
                    ref
                    for ref in api_client.app.state.files.sources(run["id"])
                    if ref["name"].startswith("tool-result-")
                )
                self.responses[2] = response(
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
            discovery_response(),
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
    assert all("read_file" in tools and "read_tool_result" in tools for tools in model.bindings)
    assert '"offset": 3000' in model.prompts[-1]
    assert [
        item["safe_details"].get("model_tool")
        for item in result["steps"]
        if item["kind"] == "tool_call"
    ] == ["search_tools", exposed_name(connection["id"], "tavily_search"), "read_tool_result"]


def test_provider_payload_is_saved_without_inferred_page_semantics(api_client, monkeypatch):
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
            discovery_response(),
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
    tool = next(item for item in result["steps"] if item["kind"] == "tool_call")
    assert tool["safe_details"]["sources"] == []
    ref = next(
        ref
        for ref in api_client.app.state.files.sources(run["id"])
        if ref["name"].startswith("tool-result-")
    )
    stored = json.loads(api_client.app.state.files.read(ref["id"]))
    assert (
        stored["data"]["structured"]["structured_content"]["results"][0]["raw_content"]
        == "fixture extracted text"
    )
    assert "extracted_urls" not in stored["platform_result"]


def test_result_reader_rechecks_originating_permission(api_client):

    from sqlalchemy import select

    from app.builtin_tools.contracts import ToolInvocation
    from app.employees.access import authorize_tool
    from app.employees.models import AgentToolGrant
    from app.errors import ConflictError
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
