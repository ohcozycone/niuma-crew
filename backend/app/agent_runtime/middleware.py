"""Compose SDK capabilities with host model execution and skill loading policies."""

import asyncio
import json
import logging

from deepagents.backends import StateBackend
from langchain.agents.middleware import (
    AgentMiddleware,
    ExtendedModelResponse,
    ModelCallLimitMiddleware,
)
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.config import get_config
from langgraph.types import Command

from app.agent_runtime.checkpoints import AgentRunState
from app.agent_runtime.contracts import AgentRequest, RuntimeControl, RuntimeFailure
from app.agent_runtime.skill_loading import (
    PreparedSkills,
    SkillLoadingMiddleware,
    build_skill_discovery_middleware,
)
from app.agent_runtime.streaming import RunProgress, truncate
from app.agent_runtime.tool_calls import ToolExecutionMiddleware
from app.llm.errors import classify_error
from app.llm.usage import aggregate_usage, parse_token_usage

logger = logging.getLogger(__name__)


class ModelExecutionMiddleware(AgentMiddleware[AgentRunState]):
    """Authorize and persist each model call, enforcing host input/output contracts."""

    state_schema = AgentRunState

    def __init__(self, input: AgentRequest, hooks: RuntimeControl, progress: RunProgress):
        self.input, self.snapshot, self.hooks, self.progress = (
            input,
            input.snapshot,
            hooks,
            progress,
        )
        self.recovered_usage = input.recovered_usage

    async def awrap_model_call(self, request, handler):
        await self.hooks.guard()
        # 保存完整历史，只在本次模型请求中选择获准的成功消息和当前执行消息。
        current = next(
            (i for i, m in enumerate(request.messages) if m.id == self.input.input_message_id),
            len(request.messages),
        )
        request = request.override(
            messages=[
                m
                for i, m in enumerate(request.messages)
                if i >= current or m.id in {m["id"] for m in self.input.messages[:-1]}
            ]
        )
        full = ([request.system_message] if request.system_message else []) + request.messages
        size = sum(len(m.model_dump_json().encode()) for m in full)
        size += len(json.dumps([convert_to_openai_tool(t) for t in request.tools]).encode())
        if size > self.snapshot["context_bytes"]:
            raise RuntimeFailure("context_limit_exceeded")
        # 宿主持久计数覆盖重启前的尝试；SDK 自身的 run_limit 仍限制单次图执行。
        round_number, key = await self.hooks.start_model()
        logger.info("model.started run=%s action=%s", self.input.run_id, key)
        self.progress.bind(key, get_config()["metadata"])
        usage = self.recovered_usage or request.state.get("model_usage", {})
        usage_accounted = False
        message = None
        try:
            response = await handler(request)
            message = response.result[0]
            if not message.tool_calls:
                message.id = self.input.output_message_id
            parsed = parse_token_usage(message.usage_metadata)
            usage = aggregate_usage(usage, parsed.model_dump() if parsed else None, round_number)
            usage_accounted = True
            self.recovered_usage = usage
            reason = message.response_metadata.get("finish_reason")
            if reason == "length":
                raise RuntimeFailure(
                    "output_limit_exceeded",
                    truncate(str(message.text), self.snapshot["max_output_bytes"])
                    if not (message.tool_calls or message.invalid_tool_calls)
                    else None,
                )
            if (
                message.invalid_tool_calls
                or (reason not in (None, "stop", "tool_calls"))
                or (reason == "tool_calls" and not message.tool_calls)
            ):
                raise RuntimeFailure("upstream_stream_error")
            if len(message.text.encode()) > self.snapshot["max_output_bytes"]:
                raise RuntimeFailure(
                    "output_limit_exceeded",
                    truncate(str(message.text), self.snapshot["max_output_bytes"])
                    if not (message.tool_calls or message.invalid_tool_calls)
                    else None,
                )
            if (
                len(json.dumps(message.tool_calls, ensure_ascii=False).encode())
                > self.snapshot["max_output_bytes"]
            ):
                raise RuntimeFailure("output_limit_exceeded")
            await self.hooks.finish(
                key,
                details={
                    "finish_reason": "tool_calls" if message.tool_calls else "stop",
                    "output_bytes": len(message.text.encode()),
                    "tool_call_ids": [
                        call["id"] for call in message.tool_calls if isinstance(call.get("id"), str)
                    ],
                },
                usage=usage,
                content=self.progress.record(key, message, complete=True)
                if message is not None
                else None,
            )
            return ExtendedModelResponse(
                model_response=response, command=Command(update={"model_usage": usage})
            )
        except asyncio.CancelledError:
            raise  # Runner atomically closes remaining steps with the run's terminal state.
        except Exception as error:
            if not usage_accounted:
                usage = aggregate_usage(usage, None, round_number)
            code = classify_error(error) or getattr(error, "code", None) or "execution_failed"
            await self.hooks.finish(
                key,
                "failed",
                code,
                usage=usage or None,
                content=self.progress.record(key, message, complete=True)
                if message is not None
                else None,
            )
            if classify_error(error):
                raise RuntimeFailure(code) from None
            raise

    async def aafter_agent(self, state, runtime):
        return {"completed_run_id": self.input.run_id}


def build_middleware(
    input: AgentRequest,
    hooks: RuntimeControl,
    progress: RunProgress,
    prepared_skills: PreparedSkills,
    *,
    backend=None,
    resources=None,
) -> list[AgentMiddleware]:
    """Build an isolated stack; skill validation must precede model execution recording."""
    backend = backend or StateBackend()
    expanded = input.snapshot.get("schema_version", 2) >= 3 and hasattr(hooks, "begin_tool")
    file_tools = sorted(
        {
            *(["read_file"] if prepared_skills.by_path else []),
            *(
                binding["tool_name"]
                for binding in input.snapshot.get("tools", [])
                if binding["kind"] == "native"
            ),
        }
    )
    return [
        *build_skill_discovery_middleware(
            backend,
            file_tools if expanded else (["read_file"] if prepared_skills.by_path else []),
            include_skills=bool(prepared_skills.by_path),
        ),
        ModelCallLimitMiddleware(
            run_limit=input.snapshot["max_model_calls"], exit_behavior="error"
        ),
        *(
            [ToolExecutionMiddleware(input.snapshot, prepared_skills, hooks, resources)]
            if expanded
            else []
        ),
        SkillLoadingMiddleware(
            prepared_skills,
            hooks,
            input.snapshot["max_skill_reads"],
            input.activated_skills,
            record_reads=not expanded,
        ),
        ModelExecutionMiddleware(input, hooks, progress),
    ]
