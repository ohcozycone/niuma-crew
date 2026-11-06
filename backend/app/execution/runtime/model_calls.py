"""Compose SDK capabilities with host model execution and skill loading policies."""

from __future__ import annotations

import asyncio
import json
import logging

from langchain.agents.middleware import (
    AgentMiddleware,
    ExtendedModelResponse,
    SummarizationMiddleware,
)
from langchain.agents.middleware.summarization import DEFAULT_SUMMARY_PROMPT
from langchain_core.messages import HumanMessage, get_buffer_string
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.config import get_config
from langgraph.types import Command

from app.execution import prompts
from app.execution.contracts import (
    AgentContext,
    AgentRequest,
    RuntimeFailure,
)
from app.execution.runtime.checkpoints import AgentRunState
from app.execution.runtime.streaming import RunProgress, truncate
from app.llm.errors import classify_error
from app.llm.factory import observe_model_request
from app.llm.usage import aggregate_usage, parse_token_usage

logger = logging.getLogger(__name__)


class ReferenceContextMiddleware(AgentMiddleware):
    """Render current references without turning them into persistent user messages."""

    def __init__(self, input: AgentRequest, context: AgentContext, knowledge_context: str = ""):
        self.context = context
        self.history_ids: set[str] = set()
        snapshot = input.snapshot
        parts = []
        if snapshot.get("memory_reset"):
            parts.append(prompts.MEMORY_RESET_NOTICE)
        evidence = snapshot.get("knowledge", {}).get("history_evidence", [])
        if evidence:
            parts.append(prompts.HISTORY_EVIDENCE_HEADER + json.dumps(evidence, ensure_ascii=False))
        if knowledge_context:
            parts.append(prompts.KNOWLEDGE_CONTEXT_HEADER + knowledge_context)
        if snapshot.get("input_files"):
            parts.append(
                prompts.INPUT_FILES_HEADER + json.dumps(snapshot["input_files"], ensure_ascii=False)
            )
        self.reference = (
            HumanMessage(id=f"run:{input.run_id}:references", content="".join(parts))
            if parts
            else None
        )

    async def awrap_model_call(self, request, handler):
        messages = []
        for message in request.messages:
            content = message.content
            if message.id in self.history_ids and self.context.clean_history:
                if isinstance(content, str):
                    content = self.context.clean_history(content)
                elif isinstance(content, list):
                    content = [
                        {**block, "text": self.context.clean_history(block["text"])}
                        if isinstance(block, dict) and isinstance(block.get("text"), str)
                        else self.context.clean_history(block)
                        if isinstance(block, str)
                        else block
                        for block in content
                    ]
            messages.append(message.model_copy(update={"content": content}))
        if self.reference is not None:
            messages.append(self.reference)
        return await handler(request.override(messages=messages))


class ModelExecutionMiddleware(AgentMiddleware[AgentRunState]):
    """Authorize and persist each model call, enforcing host input/output contracts."""

    state_schema = AgentRunState

    def __init__(
        self, input: AgentRequest, context: AgentContext, progress: RunProgress, *, usage: RunUsage
    ):
        self.input, self.context, self.progress, self.usage = input, context, progress, usage

    async def awrap_model_call(self, request, handler):
        await self.context.guard()
        full = ([request.system_message] if request.system_message else []) + request.messages
        size = sum(len(m.model_dump_json().encode()) for m in full)
        size += len(json.dumps([convert_to_openai_tool(t) for t in request.tools]).encode())
        if size > self.input.snapshot["context_bytes"]:
            raise RuntimeFailure("context_limit_exceeded")
        # 宿主持久计数覆盖重启前的尝试；SDK 自身的 run_limit 仍限制单次图执行。
        round_number, key = await self.context.start_model()
        logger.info(
            "model.started run=%s action=%s", self.input.run_id, key, extra={"action_key": key}
        )
        self.progress.bind(key, get_config()["metadata"])
        usage = self.usage.totals
        usage_accounted = False
        message = None
        try:

            async def capture(payload):
                await self.context.capture_evidence(key, "request", "wire_request", payload)

            with observe_model_request(capture):
                response = await handler(request)
            message = response.result[0]
            await self.context.capture_evidence(
                key,
                "response",
                "sdk_response",
                {
                    "content": message.content,
                    "tool_calls": message.tool_calls,
                    "invalid_tool_calls": message.invalid_tool_calls,
                    "reasoning_content": message.additional_kwargs.get("reasoning_content"),
                    "response_metadata": message.response_metadata,
                    "usage": message.usage_metadata,
                },
            )
            if not message.tool_calls:
                message.id = self.input.output_message_id
            parsed = parse_token_usage(message.usage_metadata)
            usage = self.usage.record(parsed.model_dump() if parsed else None, round_number)
            usage_accounted = True
            reason = message.response_metadata.get("finish_reason")
            if reason == "length":
                raise RuntimeFailure(
                    "output_limit_exceeded",
                    truncate(str(message.text), self.input.snapshot["max_output_bytes"])
                    if not (message.tool_calls or message.invalid_tool_calls)
                    else None,
                )
            if (
                message.invalid_tool_calls
                or (reason not in (None, "stop", "tool_calls"))
                or (reason == "tool_calls" and not message.tool_calls)
            ):
                raise RuntimeFailure("upstream_stream_error")
            if len(message.text.encode()) > self.input.snapshot["max_output_bytes"]:
                raise RuntimeFailure(
                    "output_limit_exceeded",
                    truncate(str(message.text), self.input.snapshot["max_output_bytes"])
                    if not (message.tool_calls or message.invalid_tool_calls)
                    else None,
                )
            if (
                len(json.dumps(message.tool_calls, ensure_ascii=False).encode())
                > self.input.snapshot["max_output_bytes"]
            ):
                raise RuntimeFailure("output_limit_exceeded")
            await self.context.finish(
                key,
                details={
                    "finish_reason": "tool_calls" if message.tool_calls else "stop",
                    "output_bytes": len(message.text.encode()),
                    "usage": parsed.model_dump() if parsed else None,
                    "tool_call_ids": [
                        call["id"] for call in message.tool_calls if isinstance(call.get("id"), str)
                    ],
                },
                usage=usage,
                content=self.progress.record(key, message, complete=True)
                if message is not None
                else None,
            )
            logger.info("model.finished", extra={"action_key": key})
            return ExtendedModelResponse(
                model_response=response, command=Command(update={"model_usage": usage})
            )
        except asyncio.CancelledError:
            raise  # RunService atomically closes remaining steps with the run's terminal state.
        except Exception as error:
            if not usage_accounted:
                usage = self.usage.record(None, round_number)
            upstream_code = classify_error(error)
            code = upstream_code or getattr(error, "code", None) or "execution_failed"
            if message is None:
                await self.context.capture_evidence(
                    key, "response", "model_error", {"error_code": code}
                )
            logger.warning(
                "model.failed",
                extra={"action_key": key, "error_code": code, "error_type": type(error).__name__},
            )
            await self.context.finish(
                key,
                "failed",
                code,
                usage=usage or None,
                content=self.progress.record(key, message, complete=True)
                if message is not None
                else None,
            )
            if upstream_code:
                raise RuntimeFailure(code) from None
            raise

    async def aafter_agent(self, state, runtime):
        return {"completed_run_id": self.input.run_id}


class RunUsage:
    """One per-attempt accumulator; unreported calls remain unknown after recovery."""

    def __init__(self, recovered=None):
        self.totals = recovered or {}

    def record(self, value, number):
        self.totals = aggregate_usage(self.totals, value, number)
        return self.totals


def create_summarization_middleware(
    model, snapshot: dict, context: AgentContext, usage: RunUsage
) -> SummarizationMiddleware:
    """创建摘要中间件，摘要与普通回答共用平台动作入口和用量累计器。"""

    async def summarize(messages):
        await context.guard()
        number, key = await context.start_model()
        accounted = False
        try:
            prompt = DEFAULT_SUMMARY_PROMPT.format(messages=get_buffer_string(messages))

            async def capture(payload):
                await context.capture_evidence(key, "request", "wire_request", payload)

            with observe_model_request(capture):
                response = await model.ainvoke([HumanMessage(content=prompt)])
            await context.capture_evidence(
                key,
                "response",
                "sdk_response",
                {
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                    "reasoning_content": response.additional_kwargs.get("reasoning_content"),
                    "usage": response.usage_metadata,
                },
            )
            parsed = parse_token_usage(response.usage_metadata)
            totals = usage.record(parsed.model_dump() if parsed else None, number)
            accounted = True
            if response.tool_calls or not str(response.text).strip():
                raise RuntimeFailure("empty_response")
            if response.response_metadata.get("finish_reason") == "length":
                raise RuntimeFailure("output_limit_exceeded")
            await context.finish(key, details={"purpose": "summary"}, usage=totals)
            return str(response.text).strip()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            totals = usage.totals if accounted else usage.record(None, number)
            await context.finish(
                key,
                "failed",
                classify_error(error) or getattr(error, "code", "summary_failed"),
                details={"purpose": "summary"},
                usage=totals,
            )
            raise

    return SummarizationMiddleware(
        model=model,
        trigger=("tokens", snapshot.get("summary_trigger_tokens", 16384)),
        keep=("tokens", snapshot.get("summary_keep_tokens", 4096)),
        summarizer=summarize,
    )
