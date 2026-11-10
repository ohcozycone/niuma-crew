from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal, NotRequired, Protocol, TypedDict

from app.builtin_tools.contracts import (
    ModelExposure,
    SandboxAccess,
    ToolActions,
    ToolCaller,
    ToolInvocation,
    ToolOutcome,
)


class InputMessage(TypedDict):
    id: str
    role: Literal["user", "assistant"]
    content: str


class AgentSnapshot(TypedDict):
    schema_version: int
    agent_id: str
    connection_id: str
    connection_config_revision: int
    connection_credential_revision: int
    system_prompt: str
    skills: list[dict]
    selected_skill_ids: list[str]
    recursion_limit: int
    max_model_calls: int
    max_skill_reads: int
    max_output_tokens: int
    max_output_bytes: int
    max_reasoning_bytes: int
    context_bytes: int
    run_timeout: float
    tool_catalog: NotRequired[dict]
    tools: NotRequired[list[dict]]
    workspace: NotRequired[dict]
    input_files: NotRequired[list[dict]]
    max_tool_calls: NotRequired[int]
    knowledge: NotRequired[dict]
    summary_trigger_tokens: NotRequired[int]
    summary_keep_tokens: NotRequired[int]
    memory_scope: NotRequired[str]
    memory_reset: NotRequired[bool]


class OutputFileReference(TypedDict):
    id: str
    name: str
    size: int
    media_type: str
    content_hash: str
    purpose: str


class AgentResult(TypedDict):
    output_files: list[OutputFileReference]


@dataclass(frozen=True, slots=True)
class AgentRequest:
    run_id: str
    snapshot: AgentSnapshot
    messages: list[InputMessage]
    config: object
    checkpoint_id: str | None = None
    recovered_usage: dict | None = None
    activated_skills: frozenset[str] = frozenset()
    recovered_content: tuple[ContentUpdate, ...] = ()
    thread_id: str = field(kw_only=True)
    base_checkpoint_id: str | None = None
    base_run_id: str | None = None

    @property
    def input_message_id(self) -> str:
        return self.messages[-1]["id"]

    @property
    def output_message_id(self) -> str:
        return f"run:{self.run_id}:answer"


@dataclass(frozen=True, slots=True)
class AgentOutput:
    text: str
    usage: dict[str, int | None] | None = None
    structured_result: AgentResult | None = None


@dataclass(frozen=True, slots=True)
class ContentUpdate:
    key: str
    output_text: str
    reasoning_text: str
    reasoning_truncated: bool
    has_tool_calls: bool


class AgentContext(ToolActions, Protocol):
    @property
    def tools(self) -> ToolCaller: ...

    sandbox: SandboxAccess | None

    def read_file(self, identifier: str) -> bytes: ...
    def list_sources(self) -> list[dict]: ...
    def save_source(self, name: str, data: bytes) -> dict: ...
    def save_output(self, name: str, data: bytes) -> dict: ...
    def read_skill_blob(self, content_hash: str) -> bytes: ...
    def knowledge_call(self, name: str, arguments: dict) -> ToolOutcome: ...
    async def preserve_tool_result(
        self, invocation: ToolInvocation, data: dict, status: str
    ) -> tuple: ...
    def load_tool_result(self, identifier: str) -> dict: ...
    def tool_result_aliases(self) -> dict: ...
    def read_tool_result(self, result_id: str, offset: int = 0, limit: int = 6000) -> str: ...
    def clean_history(self, content: str) -> str: ...

    async def guard(self, extra: Iterable[str] = ()) -> None: ...
    async def remaining_model_calls(self) -> int: ...
    async def start_model(self, exposure: ModelExposure) -> tuple[int, str]: ...
    async def capture_evidence(
        self, key: str, direction: str, stage: str, payload: dict
    ) -> None: ...
    async def start(
        self,
        key: str,
        kind: str,
        details: dict | None = None,
        skill_id: str | None = None,
        *,
        budget: str | None = None,
    ) -> None: ...
    async def finish(
        self,
        key: str,
        status: str = "succeeded",
        error: str | None = None,
        details: dict | None = None,
        usage: dict | None = None,
        content: ContentUpdate | None = None,
    ) -> None: ...
    async def report_content(self, update: ContentUpdate) -> None: ...
    async def checkpoint_saved(self, reference: str) -> None: ...


class AgentRuntimeContext(TypedDict):
    """由框架传递的可信宿主上下文，不进入模型工具参数。"""

    host: AgentContext
    run_id: str
