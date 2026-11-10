from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import replace
from typing import cast

from jsonschema import Draft202012Validator
from langchain.agents.middleware import (
    AgentMiddleware,
)
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

from app.agent.contracts import AgentContext
from app.agent.errors import RuntimeFailure
from app.agent.mcp_tools import bind_mcp_call, mcp_tool
from app.builtin_tools.contracts import RESULT_READER, ToolBinding, ToolInvocation, ToolOutcome
from app.builtin_tools.knowledge import knowledge_tool
from app.builtin_tools.result_files import ResultScope, result_read_hint, result_scope
from app.builtin_tools.results import (
    normalize_feedback,
    render_feedback,
    result_reader_tool,
    tool_message,
)
from app.builtin_tools.tool_search import SEARCH_TOOLS, search_tool
from app.builtin_tools.workspace import normalize_workspace
from app.environments.policy import under
from app.errors import failure_code
from app.infrastructure.concurrency import run_sync


async def _execute_tool(
    context: AgentContext,
    invocation: ToolInvocation,
    invoke: Callable[[], Awaitable[tuple[object, ToolOutcome]]],
    render_saved: Callable[[dict], object],
    *,
    input_schema: dict,
    effective_arguments: dict | None = None,
    render_outcome: Callable[[ToolOutcome], object] | None = None,
) -> object:
    permit = await context.begin_tool(invocation)
    if permit.cached is not None:
        await context.guard_tool(invocation)
        return render_saved(permit.cached)
    await context.capture_evidence(
        invocation.key,
        "request",
        "tool_request",
        {
            "name": invocation.name,
            "requested_arguments": invocation.arguments,
            "effective_arguments": effective_arguments
            if effective_arguments is not None
            else invocation.arguments,
            "authorization_status": "allowed",
        },
    )
    try:
        if Draft202012Validator(input_schema).is_valid(invocation.arguments):
            await context.guard_tool(invocation)
            result, outcome = await invoke()
            await context.guard_tool(invocation)
        else:
            outcome = ToolOutcome(
                "工具参数不符合定义，请修正后重试。", "failed", error_code="tool_arguments_invalid"
            )
            result = render_saved({"content": outcome.content, "status": outcome.status})
    except asyncio.CancelledError:
        raise
    except Exception as error:
        if failure_code(error) == "tool_arguments_invalid":
            outcome = ToolOutcome(
                "工具参数不符合定义或结果范围，请修正参数后重试。",
                "failed",
                error_code="tool_arguments_invalid",
            )
            result = render_saved({"content": outcome.content, "status": outcome.status})
        else:
            await context.complete_tool(
                permit,
                ToolOutcome(
                    "工具没有取得已确认结果。",
                    "unknown"
                    if getattr(error, "code", "") in {"tool_upstream_failed", "tool_result_unknown"}
                    else "failed",
                    error_code=failure_code(error),
                ),
            )
            raise
    # 先保存结果再反馈模型，存储失败不得放行未登记的结果。
    await context.complete_tool(permit, outcome)
    return render_outcome(outcome) if render_outcome else result


class ToolExecutionMiddleware(AgentMiddleware):
    def __init__(self, snapshot, prepared, run_id: str, adapters=None):
        self.prepared, self.run_id = prepared, run_id
        self.bindings = {binding["exposed_name"]: binding for binding in snapshot.get("tools", [])}
        self.workspace_lock = asyncio.Lock()
        self.adapters = adapters or {}

    async def awrap_tool_call(self, request, handler):
        if request.tool is None or request.tool.name != request.tool_call["name"]:
            raise RuntimeFailure("tool_not_allowed")
        _runtime_host(request.runtime, self.run_id)
        if (
            not request.runtime.tool_call_id
            or request.runtime.tool_call_id != request.tool_call["id"]
        ):
            raise RuntimeFailure("tool_not_allowed")
        binding = self.bindings.get(request.tool_call["name"])
        if binding is None or binding["kind"] == "workspace":
            async with self.workspace_lock:
                return await self._invoke(request, handler)
        return await self._invoke(request, handler)

    async def _invoke(self, request, handler):
        context = _runtime_host(request.runtime, self.run_id)
        call = request.tool_call
        resource_skill = (
            self.prepared.resource_paths.get(call.get("args", {}).get("file_path"))
            if call["name"] == "read_file"
            else None
        )
        entry = (
            self.prepared.by_path.get(call.get("args", {}).get("file_path"))
            if call["name"] == "read_file"
            else None
        )
        binding = self.bindings.get(call["name"])
        result_reader = call["name"] == RESULT_READER
        if result_reader:
            envelope = await run_sync(
                context.load_tool_result, call.get("args", {}).get("result_id")
            )
            origin = envelope["platform_result"]["binding_id"]
            binding = next(item for item in self.bindings.values() if item["binding_id"] == origin)
        skill = entry.skill if entry else resource_skill[0] if resource_skill else None
        if (
            call["name"] == "read_file"
            and isinstance(call.get("args", {}).get("file_path"), str)
            and under(call["args"]["file_path"], "/skills")
            and skill is None
        ):
            raise RuntimeFailure("skill_not_allowed")
        if skill is None and binding is None:
            path = call.get("args", {}).get("file_path")
            raise RuntimeFailure(
                "skill_not_allowed"
                if call["name"] == "read_file" and isinstance(path, str) and under(path, "/skills")
                else "tool_not_allowed"
            )
        parent = next(
            (
                message
                for message in reversed(request.runtime.state.get("messages", []))
                if isinstance(message, AIMessage)
                and any(item.get("id") == call["id"] for item in message.tool_calls)
            ),
            None,
        )
        parent_key = (
            parent.additional_kwargs.get("app_model_action_key")
            if parent and parent.additional_kwargs.get("app_run_id") == self.run_id
            else None
        )
        invocation = ToolInvocation(
            "tool:" + call["id"],
            "skill:" + skill["skill_id"]
            if skill
            else "result:" + binding["binding_id"]
            if result_reader
            else binding["binding_id"],
            call["name"],
            call.get("args", {}),
            skill["skill_id"] if skill else None,
            model_action_key=parent_key,
        )

        adapter = self.adapters.get(call["name"])
        renderer = adapter.render_saved if adapter else None
        normalizer = adapter.normalize if adapter else normalize_feedback

        def render_saved(saved):
            return (
                renderer(saved, call["id"])
                if renderer
                else render_feedback(saved, call["name"], call["id"])
            )

        async def invoke():
            tool_request = request
            if binding and binding["kind"] in ("mcp_http", "mcp_stdio") and not result_reader:
                tool_request = bind_mcp_call(request, binding, context, invocation)
            scope = ResultScope(invocation)
            token = result_scope.set(scope)
            try:
                result = await handler(tool_request)
                if scope.aliases or scope.reads:
                    message = tool_message(result)
                    if isinstance(message.content, str):
                        message.content = (
                            result_read_hint(scope, self.bindings.values()) + message.content
                        )
                outcome = await normalizer(result, invocation, context)
                if scope.aliases or scope.reads:
                    message = tool_message(result)
                    message.artifact = {
                        **(message.artifact or {}),
                        **({"result_aliases": scope.aliases} if scope.aliases else {}),
                        **({"source_reads": scope.reads} if scope.reads else {}),
                    }
                    outcome = replace(
                        outcome,
                        data={
                            **outcome.data,
                            "file_id": scope.file_id or outcome.data.get("file_id"),
                            "artifact": message.artifact,
                        },
                    )
                return result, outcome
            finally:
                result_scope.reset(token)

        return await _execute_tool(
            context,
            invocation,
            invoke,
            render_saved,
            input_schema=tool_input_schema(request.tool),
            effective_arguments={**invocation.arguments, "offset": 0, "limit": 1000000}
            if entry is not None
            else invocation.arguments,
            render_outcome=(
                lambda outcome: render_saved(
                    {"content": outcome.content, "status": outcome.status, "data": outcome.data}
                )
            )
            if renderer is not None
            else None,
        )


def _runtime_host(runtime: ToolRuntime[dict], run_id: str | None = None) -> AgentContext:
    context = runtime.context if runtime is not None else None
    if (
        not isinstance(context, dict)
        or context.get("host") is None
        or not isinstance(context.get("run_id"), str)
        or not context["run_id"]
        or (run_id is not None and context["run_id"] != run_id)
    ):
        raise RuntimeFailure("tool_not_allowed")
    return cast(AgentContext, context["host"])


async def presearch(snapshot, context: AgentContext, query: str) -> str:
    if snapshot.get("knowledge", {}).get("mode") != "always":
        return ""
    binding = next(
        b
        for b in snapshot["tools"]
        if b["kind"] == "knowledge" and b["tool_name"] == "search_knowledge"
    )
    invocation = ToolInvocation(
        "knowledge:presearch",
        binding["binding_id"],
        "search_knowledge",
        {"query": query[:1000]},
        origin="host_presearch",
    )

    async def invoke():
        await context.guard_tool(invocation)
        outcome = await run_sync(context.knowledge_call, invocation.name, invocation.arguments)
        await context.guard_tool(invocation)
        return outcome.content, outcome

    return await _execute_tool(
        context,
        invocation,
        invoke,
        lambda saved: saved["content"],
        input_schema=binding["input_schema"],
    )


def prepare_agent_tools(
    snapshot, middleware, context: AgentContext, discovery
) -> tuple[list[BaseTool], dict[str, ToolBinding]]:
    tools, adapters = [], {}
    for binding in snapshot.get("tools", []):
        prepared = None
        if binding["kind"] in ("mcp_http", "mcp_stdio"):
            prepared = mcp_tool(binding)
        elif binding["kind"] == "knowledge":
            prepared = knowledge_tool(binding, context.knowledge_call)
        elif binding["tool_name"] == RESULT_READER:
            prepared = result_reader_tool(context.read_tool_result)
        elif binding["tool_name"] == SEARCH_TOOLS:
            prepared = search_tool(discovery.search, discovery.validate_result)
        elif binding["kind"] == "workspace":
            adapters[binding["exposed_name"]] = ToolBinding(None, normalize_workspace)
        if prepared is not None:
            assert prepared.tool is not None
            tools.append(prepared.tool)
            adapters[binding["exposed_name"]] = prepared
    all_tools = list(tools)
    for item in middleware:
        all_tools.extend(getattr(item, "tools", []))
    validate_tool_names(all_tools)
    return tools, adapters


def validate_tool_names(tools: Iterable[BaseTool]) -> None:
    names: set[str] = set()
    for tool in tools:
        if tool.name in names:
            raise RuntimeFailure("tool_catalog_changed")
        names.add(tool.name)


def tool_input_schema(tool: BaseTool) -> dict:
    schema = tool.tool_call_schema
    return schema if isinstance(schema, dict) else schema.model_json_schema()
