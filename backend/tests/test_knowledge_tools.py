"""Knowledge tool schemas and model validation exercised through the real ToolNode."""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from runtime_helpers import MemoryContext, agent_runtime

from app.errors import InvalidInputError
from app.execution.contracts import AgentRuntimeContext, ToolOutcome
from app.execution.runtime.skills import prepare_skills
from app.execution.runtime.tool_calls import ToolExecutionMiddleware, prepare_agent_tools
from app.knowledge.access import KnowledgeAccess
from app.knowledge.search import tool_bindings

LIBRARY_ID = "00000000-0000-4000-8000-000000000001"
EVIDENCE_ID = "K-0123456789abcdef"


def knowledge_graph():
    context = MemoryContext()
    calls = []

    def call(name, arguments):
        parsed = KnowledgeAccess.arguments(name, arguments).model_dump(mode="json")
        calls.append((name, parsed))
        return ToolOutcome(json.dumps(parsed, ensure_ascii=False))

    context.knowledge_call = call
    snapshot = {"tools": tool_bindings()}
    tools = prepare_agent_tools(snapshot, [])
    middleware = ToolExecutionMiddleware(snapshot, prepare_skills([], []), "run")
    builder = StateGraph(MessagesState, context_schema=AgentRuntimeContext)
    builder.add_node("tools", ToolNode(tools, awrap_tool_call=middleware.awrap_tool_call))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    return builder.compile(), context, calls


def invoke(graph, context, name, arguments):
    return asyncio.run(
        graph.ainvoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{"name": name, "args": arguments, "id": "knowledge"}],
                    )
                ]
            },
            context=agent_runtime(context),
        )
    )["messages"][-1]


@pytest.mark.parametrize(
    "name,arguments",
    [
        pytest.param("search_knowledge", {"query": ""}, id="empty-query"),
        pytest.param("search_knowledge", {"query": "查" * 1001}, id="long-query"),
        pytest.param("search_knowledge", {"query": "报销", "library_ids": []}, id="empty-scope"),
        pytest.param(
            "search_knowledge",
            {"query": "报销", "library_ids": [LIBRARY_ID] * 11},
            id="large-scope",
        ),
        pytest.param(
            "search_knowledge", {"query": "报销", "user_id": "forged"}, id="extra-search-field"
        ),
        pytest.param(
            "read_knowledge_source", {"evidence_id": "not-an-evidence-id"}, id="invalid-evidence"
        ),
        pytest.param(
            "read_knowledge_source",
            {"evidence_id": EVIDENCE_ID, "offset": -1},
            id="negative-offset",
        ),
        pytest.param(
            "read_knowledge_source", {"evidence_id": EVIDENCE_ID, "offset": 2001}, id="large-offset"
        ),
        pytest.param(
            "read_knowledge_source",
            {"evidence_id": EVIDENCE_ID, "user_id": "forged"},
            id="extra-read-field",
        ),
    ],
)
def test_registered_schema_rejects_invalid_arguments_before_knowledge_call(name, arguments):
    graph, context, calls = knowledge_graph()
    result = invoke(graph, context, name, arguments)
    assert calls == []
    assert result.status == "error"
    assert context.actions["tool:knowledge"]["status"] == "failed"
    assert len(context.actions) == 1


@pytest.mark.parametrize(
    "name,arguments,expected",
    [
        ("search_knowledge", {"query": " 报销 "}, {"query": "报销", "library_ids": None}),
        (
            "search_knowledge",
            {"query": "报销", "library_ids": None},
            {"query": "报销", "library_ids": None},
        ),
        (
            "search_knowledge",
            {"query": "报销", "library_ids": [LIBRARY_ID]},
            {"query": "报销", "library_ids": [LIBRARY_ID]},
        ),
        (
            "read_knowledge_source",
            {"evidence_id": EVIDENCE_ID},
            {"evidence_id": EVIDENCE_ID, "offset": 0},
        ),
        (
            "read_knowledge_source",
            {"evidence_id": EVIDENCE_ID, "offset": 2000},
            {"evidence_id": EVIDENCE_ID, "offset": 2000},
        ),
    ],
)
def test_registered_tools_preserve_defaults_and_valid_arguments(name, arguments, expected):
    graph, context, calls = knowledge_graph()
    result = invoke(graph, context, name, arguments)
    assert calls == [(name, expected)]
    assert result.status == "success" and json.loads(result.content) == expected
    assert context.actions["tool:knowledge"]["status"] == "succeeded"
    assert len(context.actions) == 1


@pytest.mark.parametrize(
    "arguments", [{"query": " \t "}, {"query": "报销", "library_ids": ["not-a-uuid"]}]
)
def test_model_validation_keeps_constraints_not_enforced_by_json_schema(arguments):
    graph, context, calls = knowledge_graph()
    with pytest.raises(InvalidInputError) as error:
        invoke(graph, context, "search_knowledge", arguments)
    assert error.value.code == "tool_arguments_invalid"
    assert calls == []
    assert context.actions["tool:knowledge"]["status"] == "failed"
