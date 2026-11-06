"""工具目录移除后，真实 SDK 请求仍经过平台检查和持久动作入口。"""

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from runtime_helpers import MemoryContext, agent_runtime

from app.execution.contracts import (
    AgentRuntimeContext,
    RuntimeFailure,
    ToolInvocation,
    ToolOutcome,
    ToolPermit,
)
from app.execution.runtime.skills import prepare_skills
from app.execution.runtime.tool_calls import (
    ToolExecutionMiddleware,
    _execute_tool,
    prepare_agent_tools,
)


def test_preparation_checks_external_and_middleware_names_without_registering_twice():
    def read(value: str) -> str:
        return value

    external = StructuredTool.from_function(read, name="external", description="外部工具")
    attached = StructuredTool.from_function(read, name="attached", description="中间件工具")
    snapshot = {
        "tools": [
            {
                "kind": "knowledge",
                "binding_id": "external",
                "exposed_name": external.name,
                "description": external.description,
                "input_schema": external.get_input_schema().model_json_schema(),
            }
        ]
    }
    middleware = [SimpleNamespace(tools=[attached])]
    assert [tool.name for tool in prepare_agent_tools(snapshot, middleware)] == ["external"]
    with pytest.raises(RuntimeFailure, match="tool_catalog_changed"):
        prepare_agent_tools(snapshot, [SimpleNamespace(tools=[external])])
    with pytest.raises(RuntimeFailure, match="tool_catalog_changed"):
        prepare_agent_tools({}, [SimpleNamespace(tools=[attached, attached])])


@pytest.mark.parametrize("schema_kind", ["json", "pydantic"])
@pytest.mark.parametrize(
    "arguments,allowed", [({"count": 1}, True), ({"count": "bad"}, False), ({}, False)]
)
def test_registered_sdk_tool_is_validated_and_recorded_before_feedback(
    schema_kind, arguments, allowed
):
    calls = []

    def probe(count: int) -> str:
        """返回测试参数。"""
        calls.append(count)
        return str(count)

    schema = {
        "type": "object",
        "properties": {"count": {"type": "integer"}},
        "required": ["count"],
    }
    tool = StructuredTool.from_function(probe)
    if schema_kind == "json":
        tool.args_schema = schema
    control = MemoryContext()
    middleware = ToolExecutionMiddleware(
        {
            "tools": [
                {
                    "kind": "native",
                    "tool_name": "probe",
                    "exposed_name": "probe",
                    "binding_id": "binding",
                    "scope_policy": {},
                }
            ]
        },
        prepare_skills([], []),
        "run",
    )
    builder = StateGraph(MessagesState, context_schema=AgentRuntimeContext)
    builder.add_node("tools", ToolNode([tool], awrap_tool_call=middleware.awrap_tool_call))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()
    result = asyncio.run(
        graph.ainvoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "probe", "args": arguments, "id": "one"}],
                    )
                ]
            },
            context=agent_runtime(control),
        )
    )
    assert calls == ([1] if allowed else [])
    assert control.actions["tool:one"]["status"] == ("succeeded" if allowed else "failed")
    assert result["messages"][-1].status == ("success" if allowed else "error")


def test_unregistered_tool_is_rejected_before_platform_action():
    control = MemoryContext()
    middleware = ToolExecutionMiddleware({}, prepare_skills([], []), "run")

    async def forbidden(request):
        raise AssertionError("未注册工具不能执行")

    with pytest.raises(RuntimeFailure, match="tool_not_allowed"):
        asyncio.run(
            middleware.awrap_tool_call(
                SimpleNamespace(tool=None, tool_call={"name": "unknown"}), forbidden
            )
        )
    assert not control.actions


def test_executor_reuses_cached_outcome_without_reexecuting(monkeypatch):
    control = MemoryContext()
    invocation = ToolInvocation("call", "binding", "probe", {})

    async def cached(invocation):
        return ToolPermit(invocation.key, invocation.fingerprint, {"content": "已保存结果"})

    async def forbidden():
        raise AssertionError("已保存的只读结果不能重新执行")

    monkeypatch.setattr(control, "begin_tool", cached)
    result = asyncio.run(
        _execute_tool(
            control,
            invocation,
            forbidden,
            lambda saved: saved["content"],
            input_schema={"required": ["missing"]},
        )
    )
    assert result == "已保存结果" and not control.actions


def test_executor_does_not_release_feedback_when_saving_fails(monkeypatch):
    control = MemoryContext()
    invocation = ToolInvocation("call", "binding", "probe", {})

    async def invoke():
        return "工具结果", ToolOutcome("工具结果")

    async def fail_save(permit, outcome):
        raise RuntimeError("保存失败")

    monkeypatch.setattr(control, "complete_tool", fail_save)
    with pytest.raises(RuntimeError, match="保存失败"):
        asyncio.run(
            _execute_tool(
                control, invocation, invoke, lambda saved: saved["content"], input_schema={}
            )
        )
    assert control.actions["call"]["status"] == "running"
