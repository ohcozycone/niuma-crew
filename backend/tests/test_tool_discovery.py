from contextlib import closing

import pytest
from test_agent_foundations import SearchClient, search_grant, send
from test_capability_runtime import ScriptedModel, discovery_response, execute, response, setup

from app.agent.tool_discovery import ToolDiscovery
from app.builtin_tools.contracts import catalog_hash
from app.builtin_tools.tool_search import search_binding, search_tool
from app.mcp.contracts import exposed_name


def test_search_expands_next_request_and_saves_exact_parent_exposure(api_client, monkeypatch):
    _, _, employee, conversation = setup(api_client)
    connection = search_grant(api_client, employee)
    name = exposed_name(connection["id"], "tavily_search")
    accepted = send(api_client, conversation)
    model = ScriptedModel(
        responses=[
            discovery_response(),
            response("", [{"name": name, "id": "lookup", "args": {"query": "网页"}}]),
            response("已查询。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert name not in model.bindings[0] and "search_tools" in model.bindings[0]
    assert name in model.bindings[1]
    actions = result["steps"]
    discovery = next(
        item for item in actions if item["safe_details"].get("category") == "tool_discovery"
    )
    assert discovery["safe_details"]["matched_count"] == 1
    assert "query" not in discovery["safe_details"] or discovery["safe_details"]["query"] == ""
    lookup = next(item for item in actions if item["action_key"] == "tool:lookup")
    parent = next(item for item in actions if item["id"] == lookup["parent_action_id"])
    assert lookup["safe_details"]["binding_id"] in parent["safe_details"]["exposed_tool_ids"]
    first = next(item for item in actions if item["action_key"] == "model:1")
    assert lookup["safe_details"]["binding_id"] not in first["safe_details"]["exposed_tool_ids"]


def test_parallel_search_cannot_authorize_same_response_guess(api_client, monkeypatch):
    _, _, employee, conversation = setup(api_client)
    connection = search_grant(api_client, employee)
    name = exposed_name(connection["id"], "tavily_search")
    accepted = send(api_client, conversation)
    SearchClient.calls = 0
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {"name": "search_tools", "id": "discover", "args": {"query": "tavily"}},
                    {"name": name, "id": "guessed", "args": {"query": "网页"}},
                ],
            )
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "failed" and result["error"]["code"] == "tool_not_allowed"
    assert SearchClient.calls == 0


def fixture_snapshot():
    tools = [
        {
            "binding_id": "tool:one",
            "kind": "mcp_http",
            "connection_id": "source",
            "tool_name": "searchPages",
            "exposed_name": "opaque",
            "description": "Search pages in a workspace",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Page title keywords"}},
            },
        },
        search_binding(),
    ]
    sources = {
        "source": {
            "service_name": "Notion",
            "connection_name": "组织资料",
            "server_instructions": "Source specific instructions",
        }
    }
    return {
        "tools": tools,
        "tool_catalog": {"sources": sources, "catalog_hash": catalog_hash(tools, sources)},
    }


@pytest.mark.parametrize("query", ["search pages", "searchPages", "page_title", 'pages " OR *'])
def test_index_uses_names_parameters_and_escaped_terms(query):
    with closing(ToolDiscovery(fixture_snapshot())) as discovery:
        result = discovery.search(query)
        assert result.data["discovery"]["matched_ids"] == ["tool:one"]
        assert discovery.search("pages", "foreign").status == "failed"
        assert discovery.search("pages", limit=11).status == "failed"


def test_cached_discovery_feedback_rebuilds_command_with_current_call_id():
    with closing(ToolDiscovery(fixture_snapshot())) as discovery:
        result = discovery.search("search pages")
        binding = search_tool(discovery.search, discovery.validate_result)
        saved = {"content": result.content, "status": result.status, "data": result.data}
        command = binding.render_saved(saved, "current")
        assert command.update["messages"][0].tool_call_id == "current"
        assert command.update["discovered_tool_ids"] == ["tool:one"]
        saved["data"]["discovery"]["catalog_hash"] = "foreign"
        with pytest.raises(Exception, match="tool_catalog_changed"):
            binding.render_saved(saved, "current")


def test_new_run_clears_discovery_without_deleting_conversation_history(api_client, monkeypatch):
    _, _, employee, conversation = setup(api_client)
    connection = search_grant(api_client, employee)
    name = exposed_name(connection["id"], "tavily_search")
    first = send(api_client, conversation)
    model = ScriptedModel(responses=[discovery_response(), response("第一轮完成")])
    assert execute(api_client, monkeypatch, model, first)["status"] == "succeeded"
    assert name in model.bindings[-1]
    second = send(api_client, conversation)
    following = ScriptedModel(responses=[response("第二轮无需工具")])
    assert execute(api_client, monkeypatch, following, second)["status"] == "succeeded"
    assert name not in following.bindings[0]
    history = api_client.get(f"/api/conversations/{conversation['id']}/messages").json()["items"]
    assert any(item["content"] == "第一轮完成" for item in history)


def test_official_parallel_commands_union_only_after_results_are_saved():
    import asyncio

    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, StateGraph
    from langgraph.prebuilt import ToolNode
    from runtime_helpers import MemoryContext, agent_runtime

    from app.agent.checkpoints import AgentRunState
    from app.agent.skills import prepare_skills
    from app.agent.tool_calls import ToolExecutionMiddleware

    snapshot = fixture_snapshot()
    second = {
        **snapshot["tools"][0],
        "binding_id": "tool:two",
        "tool_name": "deleteRecord",
        "exposed_name": "second",
        "description": "Delete records",
    }
    snapshot["tools"].append(second)
    snapshot["tool_catalog"]["catalog_hash"] = catalog_hash(
        snapshot["tools"], snapshot["tool_catalog"]["sources"]
    )
    with closing(ToolDiscovery(snapshot)) as discovery:
        binding = search_tool(discovery.search, discovery.validate_result)
        host = MemoryContext()
        middleware = ToolExecutionMiddleware(
            snapshot, prepare_skills([], []), "run", {"search_tools": binding}
        )
        builder = StateGraph(AgentRunState)
        builder.add_node(
            "tools", ToolNode([binding.tool], awrap_tool_call=middleware.awrap_tool_call)
        )
        builder.add_edge(START, "tools")
        builder.add_edge("tools", END)
        graph = builder.compile()
        value = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_tools",
                            "id": "one",
                            "args": {"query": "pages", "limit": 1},
                        },
                        {
                            "name": "search_tools",
                            "id": "two",
                            "args": {"query": "delete", "limit": 1},
                        },
                        {"name": "search_tools", "id": "empty", "args": {"query": "nonexistent"}},
                    ],
                )
            ]
        }
        result = asyncio.run(graph.ainvoke(value, context=agent_runtime(host)))
        assert result["discovered_tool_ids"] == ["tool:one", "tool:two"]
        assert all(item["status"] == "succeeded" for item in host.actions.values())


def test_model_exposure_cannot_be_overwritten_or_reused_for_hidden_tool(api_client):
    from app.builtin_tools.contracts import ToolInvocation
    from app.execution.errors import ExecutionFailure

    _, _, employee, conversation = setup(api_client)
    connection = search_grant(api_client, employee)
    accepted = send(api_client, conversation)
    store = api_client.app.state.run_worker.store
    assert store.claim(accepted["id"])
    row, _ = store.load(accepted["id"])
    name = exposed_name(connection["id"], "tavily_search")
    tool = next(item for item in row.config_snapshot["tools"] if item["exposed_name"] == name)
    _, key = store.start_model(
        row.id,
        lambda db: None,
        exposure={
            "catalog_hash": row.config_snapshot["tool_catalog"]["catalog_hash"],
            "exposed_tool_ids": ["builtin:search_tools"],
        },
    )
    with pytest.raises(ExecutionFailure, match="runtime_interrupted"):
        store.finish_action(row.id, key, details={"exposed_tool_ids": [tool["binding_id"]]})
    store.finish_action(
        row.id,
        key,
        details={"tool_call_ids": ["guess"], "tool_calls": [{"id": "guess", "name": name}]},
    )
    invocation = ToolInvocation(
        "tool:guess", tool["binding_id"], name, {"query": "x"}, model_action_key=key
    )
    with pytest.raises(ExecutionFailure, match="tool_not_allowed"):
        store.begin_tool(row.id, invocation, lambda db: tool)
    assert store.load(row.id)[0].tool_calls == 0


@pytest.mark.parametrize(
    "count,description,code",
    [
        pytest.param(129, "short", "tool_candidate_count_exceeded", id="count"),
        pytest.param(1, "x" * 1048576, "tool_candidate_bytes_exceeded", id="bytes"),
    ],
)
def test_candidate_budgets_fail_independently_of_model_context(
    api_client, monkeypatch, count, description, code
):
    from app.employees.assembly import capture_tools

    _, _, employee, conversation = setup(api_client)
    search_grant(api_client, employee)
    with api_client.app.state.database.transaction() as db:
        bindings, _ = capture_tools(db, employee["id"])
    original = bindings[0]
    candidates = [
        {
            **original,
            "binding_id": f"candidate:{i}",
            "exposed_name": f"candidate_{i}",
            "description": description,
        }
        for i in range(count)
    ]
    monkeypatch.setattr("app.execution.snapshot.capture_tools", lambda *_: (candidates, False))
    from uuid import uuid4

    accepted = api_client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "检查边界", "client_request_id": str(uuid4())},
    )
    assert accepted.status_code == 422 and accepted.json()["detail"]["code"] == code


def test_real_catalog_keyword_queries_meet_recall_gate():
    import json
    from pathlib import Path

    fixture = json.loads(
        (Path(__file__).parent / "fixtures/tool-discovery-catalog.json").read_text()
    )
    cases = json.loads(
        (Path(__file__).parent / "fixtures/tool-discovery-queries.json").read_text()
    )["cases"]
    tools, sources = [], {}
    for source in fixture["sources"]:
        key = source["source"]
        sources[key] = {"service_name": key, "connection_name": key, "server_instructions": ""}
        for item in source["tools"]:
            tools.append(
                {
                    "kind": "mcp_http",
                    "binding_id": key + ":" + item["name"],
                    "connection_id": key,
                    "tool_name": item["name"],
                    "exposed_name": f"fixture_{len(tools)}",
                    "description": item["description"],
                    "input_schema": item["input_schema"],
                }
            )
    tools.append(search_binding())
    snapshot = {
        "tools": tools,
        "tool_catalog": {"sources": sources, "catalog_hash": catalog_hash(tools, sources)},
    }
    with closing(ToolDiscovery(snapshot)) as index:
        hits = [
            any(
                key.endswith(":" + case["expected"])
                for key in index.search(case["query"]).data["discovery"]["matched_ids"]
            )
            for case in cases
        ]
        assert sum(hits) / len(cases) >= 0.95
        assert all(hits), [case["request"] for case, hit in zip(cases, hits) if not hit]


def test_parameter_index_handles_boolean_combinations_and_bounded_nesting():
    from app.agent.tool_discovery import parameter_text

    value = {
        "properties": {
            "flag": True,
            "disabled": False,
            "records": {
                "type": "array",
                "items": {
                    "oneOf": [
                        True,
                        {"properties": {"title": {"description": "Page title keywords"}}},
                    ]
                },
            },
        },
        "allOf": [{"description": "Required scope"}],
        "$ref": "https://example.invalid/never-fetch",
    }
    text = parameter_text(value)
    assert all(
        term in text
        for term in (
            "flag",
            "disabled",
            "records",
            "title",
            "Page title keywords",
            "Required scope",
        )
    )
    assert "never-fetch" not in text
    cyclic = {"description": "bounded"}
    cyclic["properties"] = {"again": cyclic}
    assert len(parameter_text(cyclic)) < 65536


def test_revocation_after_discovery_stops_before_next_model_request(api_client, monkeypatch):
    from sqlalchemy import select

    from app.employees.models import AgentToolGrant
    from app.execution.context import RunContext

    _, _, employee, conversation = setup(api_client)
    search_grant(api_client, employee)
    original = RunContext.complete_tool

    async def save_then_revoke(host, permit, outcome):
        await original(host, permit, outcome)
        if outcome.data.get("discovery"):
            with api_client.app.state.database.transaction() as db:
                grant = db.scalar(
                    select(AgentToolGrant).where(AgentToolGrant.agent_id == employee["id"])
                )
                grant.enabled = False

    monkeypatch.setattr(RunContext, "complete_tool", save_then_revoke)
    accepted = send(api_client, conversation)
    model = ScriptedModel(responses=[discovery_response(), response("不应请求模型")])
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "failed" and result["error"]["code"] == "tool_access_revoked"
    assert len(model.prompts) == 1
    assert len([item for item in result["steps"] if item["kind"] == "model_call"]) == 1


def test_parallel_discovery_union_over_context_never_sends_next_request(api_client, monkeypatch):
    from sqlalchemy import select

    from app.employees.models import AgentToolGrant
    from app.values import digest

    original = SearchClient.catalog[0]
    catalog = [
        {
            **original,
            "name": original["name"] if word == "alpha" else f"{word}_search",
            "description": word + " " + filler * 35000,
            "descriptor_hash": digest(word),
        }
        for word, filler in (("alpha", "x "), ("beta", "y "))
    ]
    monkeypatch.setattr(SearchClient, "catalog", catalog)
    _, _, employee, conversation = setup(api_client)
    search_grant(api_client, employee)
    with api_client.app.state.database.transaction() as db:
        grant = db.scalar(select(AgentToolGrant).where(AgentToolGrant.agent_id == employee["id"]))
        grant.tools = [
            {"name": item["name"], "descriptor_hash": item["descriptor_hash"]} for item in catalog
        ]
    accepted = send(api_client, conversation)
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {"name": "search_tools", "id": word, "args": {"query": word, "limit": 1}}
                    for word in ("alpha", "beta")
                ],
            ),
            response("不应请求模型"),
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "failed" and result["error"]["code"] == "context_limit_exceeded"
    assert len(model.prompts) == 1
    discoveries = [
        item for item in result["steps"] if item["safe_details"].get("category") == "tool_discovery"
    ]
    assert len(discoveries) == 2 and all(
        item["status"] == "succeeded" and item["safe_details"]["matched_count"] == 1
        for item in discoveries
    )


def test_discovery_result_save_failure_never_emits_command(api_client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    _, _, employee, conversation = setup(api_client)
    search_grant(api_client, employee)
    store = api_client.app.state.run_worker.store
    original = store.finish_action
    converted = []
    render = ToolDiscovery.validate_result

    def fail_save(*args, **kwargs):
        if kwargs.get("result_payload", {}).get("data", {}).get("discovery"):
            raise OperationalError("injected", {}, Exception("injected"))
        return original(*args, **kwargs)

    def convert(index, value):
        converted.append(value)
        return render(index, value)

    monkeypatch.setattr(store, "finish_action", fail_save)
    monkeypatch.setattr(ToolDiscovery, "validate_result", convert)
    accepted = send(api_client, conversation)
    model = ScriptedModel(responses=[discovery_response(), response("不应继续")])
    with pytest.raises(OperationalError):
        execute(api_client, monkeypatch, model, accepted)
    assert len(model.prompts) == 1 and converted == []
