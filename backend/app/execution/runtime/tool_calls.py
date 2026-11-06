"""Compose SDK capabilities with host model execution and skill loading policies."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterable
from typing import cast

from jsonschema import Draft202012Validator
from langchain.agents.middleware import (
    AgentMiddleware,
    ToolCallRequest,
)
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import Command

from app.environments.policy import under
from app.execution import prompts
from app.execution.contracts import (
    RESULT_READER,
    AgentContext,
    RuntimeFailure,
    ToolInvocation,
    ToolOutcome,
    ToolReadObservation,
)
from app.execution.runtime.concurrency import run_sync


async def _execute_tool(
    context: AgentContext,
    invocation: ToolInvocation,
    invoke: Callable[[], Awaitable[tuple[object, ToolOutcome]]],
    render_saved: Callable[[dict], object],
    *,
    input_schema: dict,
) -> object:
    permit = await context.begin_tool(invocation)
    if permit.cached is not None:
        return render_saved(permit.cached)
    try:
        if Draft202012Validator(input_schema).is_valid(invocation.arguments):
            result, outcome = await invoke()
        else:
            outcome = ToolOutcome("工具参数不符合定义，请修正后重试。", "failed")
            result = render_saved({"content": outcome.content, "status": outcome.status})
    except asyncio.CancelledError:
        raise
    except Exception as error:
        await context.complete_tool(
            permit,
            ToolOutcome(
                "工具没有取得已确认结果。",
                "unknown"
                if getattr(error, "code", "") in {"tool_upstream_failed", "tool_result_unknown"}
                else "failed",
            ),
        )
        raise
    # A storage failure here must not release unrecorded feedback to the model.
    await context.complete_tool(permit, outcome)
    return result


def tool_message(result):
    if isinstance(result, ToolMessage):
        return result
    if isinstance(result, Command):
        return next(
            (
                value
                for value in reversed(result.update.get("messages", []))
                if isinstance(value, ToolMessage)
            ),
            None,
        )
    return None


class ToolExecutionMiddleware(AgentMiddleware):
    def __init__(self, snapshot, prepared, run_id: str):
        self.prepared, self.run_id = prepared, run_id
        self.bindings = {binding["exposed_name"]: binding for binding in snapshot.get("tools", [])}
        self.workspace_lock = asyncio.Lock()

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
        if binding is None or binding["kind"] == "native":
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
        if skill is None and binding is None:
            path = call.get("args", {}).get("file_path")
            raise RuntimeFailure(
                "skill_not_allowed"
                if call["name"] == "read_file" and isinstance(path, str) and under(path, "/skills")
                else "tool_not_allowed"
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
        )

        def render_saved(saved):
            return ToolMessage(
                content=saved["content"],
                name=call["name"],
                tool_call_id=call["id"],
                status="success" if saved["status"] == "succeeded" else "error",
            )

        async def invoke():
            tool_request = request
            if binding and binding["kind"] in ("mcp_http", "mcp_stdio") and not result_reader:
                tool_request = _bind_mcp_call(request, binding, context, invocation)
            effective = dict(call.get("args", {}))
            if entry is not None:
                effective.update(offset=0, limit=1000000)
            await context.capture_evidence(
                invocation.key,
                "request",
                "tool_request",
                {
                    "name": invocation.name,
                    "requested_arguments": invocation.arguments,
                    "effective_arguments": effective,
                    "authorization_status": "allowed",
                },
            )
            result = await handler(tool_request)
            message = tool_message(result)
            if message is None:
                raise RuntimeFailure("tool_result_unknown")
            content = (
                message.content
                if isinstance(message.content, str)
                else json.dumps(message.content, ensure_ascii=False)
            )
            status = "succeeded" if message.status == "success" else "failed"
            data, sources = {}, ()
            artifact = message.artifact or {}
            if isinstance(artifact, dict) and "platform_outcome" in artifact:
                external = artifact["platform_outcome"]
                status = external["status"]
                content, data, sources = await context.preserve_tool_result(
                    invocation, external["data"], status
                )
                if sources and all(source["status"] == "failed" for source in sources):
                    status = "failed"
                message.artifact = {"file_id": data["file_id"]}
                message.status = "success" if status == "succeeded" else "error"
            elif isinstance(artifact, dict) and "knowledge_outcome" in artifact:
                knowledge = artifact["knowledge_outcome"]
                status, data, sources = (
                    knowledge["status"],
                    knowledge["data"],
                    tuple(knowledge["sources"]),
                )
                message.status = "success" if status == "succeeded" else "error"
                message.artifact = None
            elif isinstance(artifact, dict) and "exit_code" in artifact:
                data = {"exit_code": artifact["exit_code"]}
                if artifact["exit_code"] != 0:
                    status = "failed"
            if entry is None:
                content = content.encode()[:24576].decode("utf-8", errors="ignore")
                message.content = content
            outcome = ToolOutcome(content, status, data, sources)
            return result, outcome

        return await _execute_tool(
            context,
            invocation,
            invoke,
            render_saved,
            input_schema=tool_input_schema(request.tool),
        )


def _runtime_host(runtime: ToolRuntime[dict], run_id: str | None = None) -> AgentContext:
    """Reject absent or mismatched trusted context before requesting a platform action."""
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


def _bind_mcp_call(
    request: ToolCallRequest, binding: dict, context: AgentContext, invocation: ToolInvocation
) -> ToolCallRequest:
    """Bind a single call without adding hidden fields to a remote tool's schema."""

    async def call(**arguments):
        outcome = await context.tools.call(
            binding, arguments, lambda: context.guard_tool(invocation)
        )
        return outcome.content, {
            "platform_outcome": {"status": outcome.status, "data": outcome.data}
        }

    # Never mutate a registered tool: parallel calls must keep independent closures.
    return request.override(tool=request.tool.model_copy(update={"coroutine": call}))


def _tool_from_binding(binding: dict) -> StructuredTool:
    """Register the captured schema; inject runtime only into platform-owned tools."""

    async def call(runtime: ToolRuntime[dict], **arguments):
        context = _runtime_host(runtime)
        if not runtime.tool_call_id:
            raise RuntimeFailure("tool_not_allowed")
        invocation = ToolInvocation(
            "tool:" + runtime.tool_call_id,
            binding["binding_id"],
            binding["exposed_name"],
            arguments,
        )
        outcome = await knowledge_call(context, invocation)
        return outcome.content, {
            "knowledge_outcome": {
                "status": outcome.status,
                "data": outcome.data,
                "sources": list(outcome.sources),
            }
        }

    return StructuredTool(
        name=binding["exposed_name"],
        description=binding["description"],
        args_schema=binding["input_schema"],
        coroutine=call if binding["kind"] == "knowledge" else None,
        response_format="content_and_artifact",
    )


async def knowledge_call(context: AgentContext, invocation: ToolInvocation) -> ToolOutcome:
    callback = context.knowledge_call
    if callback is None:
        raise RuntimeFailure("tool_not_allowed")
    await context.guard_tool(invocation)
    outcome = await run_sync(callback, invocation.name, invocation.arguments)
    await context.guard_tool(invocation)
    return outcome


async def presearch(snapshot, context: AgentContext, query: str) -> str:
    """Stable readonly action permits restart reuse, with authorization before every reuse."""
    if snapshot.get("knowledge", {}).get("mode") != "always":
        return ""
    invocation = ToolInvocation(
        "knowledge:presearch",
        next(
            b["binding_id"]
            for b in snapshot["tools"]
            if b["kind"] == "knowledge" and b["tool_name"] == "search_knowledge"
        ),
        "search_knowledge",
        {"query": query[:1000]},
    )
    permit = await context.begin_tool(invocation)
    if permit.cached is not None:
        await context.guard_tool(invocation)
        return permit.cached["content"]
    try:
        outcome = await knowledge_call(context, invocation)
    except Exception:
        await context.complete_tool(permit, ToolOutcome("知识预检索未取得已确认结果。", "failed"))
        raise
    await context.complete_tool(permit, outcome)
    return outcome.content


def result_reader_tool() -> StructuredTool:
    # Tool schemas are built by Pydantic; the live host Protocol must stay opaque inside dict.
    def read_tool_result(
        result_id: str,
        runtime: ToolRuntime[dict],
        offset: int = 0,
        limit: int = 6000,
    ) -> str:
        return _runtime_host(runtime).read_tool_result(result_id, offset, limit)

    return StructuredTool.from_function(
        read_tool_result,
        name=RESULT_READER,
        description=prompts.TOOL_RESULT_READER_DESCRIPTION,
    )


def read_observations(messages):
    observations = []
    for message in messages:
        if not isinstance(message, ToolMessage) or message.status != "success":
            continue
        try:
            value = json.loads(message.content)
        except (TypeError, ValueError):
            continue
        if not isinstance(value, dict) or not isinstance(value.get("result_id"), str):
            continue
        start, end = (
            (value.get("offset"), value.get("end"))
            if message.name == RESULT_READER
            else (0, value.get("preview_end"))
        )
        if type(start) is int and type(end) is int:
            observations.append(ToolReadObservation(value["result_id"], start, end))
    return observations


async def verify_tool_reads(context: AgentContext, question: str, messages) -> None:
    """将 SDK 工具消息转换成普通来源证据，再交给平台核验网页读取。"""
    if context.verify_web_reads:
        await run_sync(context.verify_web_reads, question, read_observations(messages))


def prepare_agent_tools(snapshot, middleware) -> list[BaseTool]:
    """准备直接注册的工具，并与中间件工具一起检查名称冲突。"""
    bindings = snapshot.get("tools", [])
    tools = [
        _tool_from_binding(binding)
        for binding in bindings
        if binding["kind"] in ("mcp_http", "mcp_stdio")
    ]
    if tools:
        tools.append(result_reader_tool())
    tools.extend(
        _tool_from_binding(binding) for binding in bindings if binding["kind"] == "knowledge"
    )
    all_tools = list(tools)
    for item in middleware:
        all_tools.extend(getattr(item, "tools", []))
    validate_tool_names(all_tools)
    return tools


def validate_tool_names(tools: Iterable[BaseTool]) -> None:
    """拒绝同名工具，避免 SDK 注册时相互覆盖。"""
    names: set[str] = set()
    for tool in tools:
        if tool.name in names:
            raise RuntimeFailure("tool_catalog_changed")
        names.add(tool.name)


def tool_input_schema(tool: BaseTool) -> dict:
    """将当前工具的输入定义转换为平台执行器使用的 JSON Schema。"""
    schema = tool.tool_call_schema
    return schema if isinstance(schema, dict) else schema.model_json_schema()
