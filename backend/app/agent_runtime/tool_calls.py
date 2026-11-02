"""One host gate around SDK file tools and MCP-backed LangChain tools."""

import asyncio
import json
from contextvars import ContextVar
from datetime import UTC, datetime

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.types import Command

from app.agent_runtime.contracts import RuntimeFailure
from app.agent_runtime.tool_results import (
    PREVIEW_CHARS,
    RESULT_READER,
    ToolResults,
    extracted_targets,
    result_text,
    structured_payload,
)
from app.tools.contracts import ToolInvocation, ToolOutcome
from app.tools.policy import under

_current_invocation: ContextVar[ToolInvocation | None] = ContextVar("tool_invocation", default=None)


def external_tools(snapshot, resources, hooks):
    from app.agent_runtime.knowledge import tools as knowledge_tools

    tools = []
    for binding in snapshot.get("tools", []):
        if binding["kind"] not in ("mcp_http", "mcp_stdio"):
            continue

        def make_call(current):
            async def call(**arguments):
                invocation = _current_invocation.get()
                if invocation is None or invocation.binding_id != current["binding_id"]:
                    raise RuntimeFailure("tool_not_allowed")
                outcome = await resources.tools.call(
                    current, arguments, lambda: hooks.guard_tool(invocation)
                )
                return outcome.content, {
                    "platform_outcome": {"status": outcome.status, "data": outcome.data}
                }

            return call

        tools.append(
            StructuredTool(
                name=binding["exposed_name"],
                description=binding["description"],
                args_schema=binding["input_schema"],
                coroutine=make_call(binding),
                response_format="content_and_artifact",
            )
        )
    if tools:
        tools.append(ToolResults(snapshot, resources).reader_tool())
    return tools + knowledge_tools(snapshot, resources, hooks, _current_invocation.get)


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
    def __init__(self, snapshot, prepared, hooks, resources):
        self.snapshot, self.prepared, self.hooks, self.resources = (
            snapshot,
            prepared,
            hooks,
            resources,
        )
        self.bindings = {binding["exposed_name"]: binding for binding in snapshot.get("tools", [])}
        self.source_files_readable = any(
            binding["kind"] == "native"
            and binding["tool_name"] == "read_file"
            and "/sources" in binding["scope_policy"].get("read_roots", [])
            for binding in snapshot.get("tools", [])
        )
        self.workspace_lock = asyncio.Lock()
        self.results = ToolResults(snapshot, resources) if resources else None

    async def _preserve_external(self, invocation, data, status):
        raw = result_text(data)
        binding = self.bindings[invocation.name]
        envelope = {
            "platform_result": {
                "binding_id": binding["binding_id"],
                "extracted_urls": extracted_targets(binding["tool_name"], data, status),
            },
            "data": data,
        }
        ref = await asyncio.to_thread(
            self.resources.save_source,
            "tool-result-" + invocation.key.removeprefix("tool:")[:64] + ".json",
            json.dumps(envelope, ensure_ascii=False).encode(),
        )
        raw_path = f"/sources/{ref['id']}/{ref['name']}"
        payload = structured_payload(data)
        sources = []
        for failed, items in (
            ((False, payload.get("results", [])), (True, payload.get("failed_results", [])))
            if isinstance(payload, dict)
            else ()
        ):
            for page in items[:16] if isinstance(items, list) else []:
                if not isinstance(page, dict):
                    continue
                source = {
                    "url": page.get("url"),
                    "title": str(page.get("title", ""))[:200],
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "status": "failed" if failed else "succeeded",
                    "full_text": False,
                    "content_kind": "extracted"
                    if binding["tool_name"] == "tavily_extract"
                    else "snippet",
                    "file_id": ref["id"],
                    "path": raw_path,
                }
                text = page.get("raw_content") or page.get("content")
                source["text_obtained"] = (
                    isinstance(text, str) and bool(text.strip()) and not failed
                )
                if binding["tool_name"] == "tavily_extract" and not (
                    isinstance(text, str) and text.strip()
                ):
                    source.update(status="failed", full_text=False)
                if isinstance(text, str) and not failed:
                    page_ref = await asyncio.to_thread(
                        self.resources.save_source, f"page-{len(sources) + 1}.txt", text.encode()
                    )
                    source.update(
                        file_id=page_ref["id"], path=f"/sources/{page_ref['id']}/{page_ref['name']}"
                    )
                sources.append(source)
        preview = raw[:PREVIEW_CHARS]
        # Downloadable result files do not grant the model filesystem access.
        # Only advertise paths it can actually read through the authorized tool.
        model_result = {
            "preview": preview,
            "result_id": ref["id"],
            "preview_end": len(preview),
            "total_chars": len(raw),
            "next_offset": len(preview) if len(preview) < len(raw) else None,
            "truncated": len(preview) < len(raw),
            "source_files_readable": self.source_files_readable,
            "sources": sources
            if self.source_files_readable
            else [
                {key: value for key, value in source.items() if key != "path"} for source in sources
            ],
        }
        if self.source_files_readable:
            model_result["raw_result"] = raw_path
        content = json.dumps(model_result, ensure_ascii=False)
        # Keep valid JSON even for large URLs/descriptions. Dropping optional
        # preview entries must not destroy the cursor for the immutable result.
        while len(content.encode()) > 24000:
            if model_result["sources"]:
                model_result["sources"] = model_result["sources"][:-1]
            else:
                model_result["preview"] = model_result["preview"][
                    : len(model_result["preview"]) // 2
                ]
                model_result["preview_end"] = len(model_result["preview"])
                model_result["next_offset"] = model_result["preview_end"]
                model_result["truncated"] = True
            content = json.dumps(model_result, ensure_ascii=False)
        return (
            content,
            {"file_id": ref["id"], "query": invocation.arguments.get("query")},
            tuple(sources),
        )

    async def awrap_tool_call(self, request, handler):
        binding = self.bindings.get(request.tool_call["name"])
        if binding is None or binding["kind"] == "native":
            async with self.workspace_lock:
                return await self._invoke(request, handler)
        return await self._invoke(request, handler)

    async def _invoke(self, request, handler):
        call = request.tool_call
        resource_skill = (
            getattr(self.prepared, "resource_paths", {}).get(call.get("args", {}).get("file_path"))
            if call["name"] == "read_file"
            else None
        )
        entry = (
            self.prepared.by_path.get(call.get("args", {}).get("file_path"))
            if call["name"] == "read_file"
            else None
        )
        binding = self.bindings.get(call["name"])
        result_reader = call["name"] == RESULT_READER and self.results is not None
        if result_reader:
            envelope = await asyncio.to_thread(
                self.results.load, call.get("args", {}).get("result_id")
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
        permit = await self.hooks.begin_tool(invocation)
        if permit.cached is not None:
            return ToolMessage(
                content=permit.cached["content"],
                name=call["name"],
                tool_call_id=call["id"],
                status="success" if permit.cached["status"] == "succeeded" else "error",
            )
        token = _current_invocation.set(invocation)
        try:
            result = await handler(request)
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
                content, data, sources = await self._preserve_external(
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
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self.hooks.complete_tool(
                permit,
                ToolOutcome(
                    "工具没有取得已确认结果。",
                    "unknown"
                    if getattr(error, "code", "") in {"tool_upstream_failed", "tool_result_unknown"}
                    else "failed",
                ),
            )
            raise
        finally:
            _current_invocation.reset(token)
        # If this transaction fails, leave the action unknown and stop the Run;
        # never return a tool message whose result was not durably recorded.
        await self.hooks.complete_tool(permit, outcome)
        return result
