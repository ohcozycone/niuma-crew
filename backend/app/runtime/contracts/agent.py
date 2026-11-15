from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import NotRequired, Protocol, TypedDict

from app.infrastructure.settings import validate_positive
from app.runtime.contracts.content import AgentResult, ContentUpdate, InputMessage, KnowledgeResult
from app.runtime.contracts.tools import (
    ModelExposure,
    SandboxAccess,
    ToolActions,
    ToolCaller,
    ToolInvocation,
    ToolOutcome,
)


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
    allow_web_access: NotRequired[bool]


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


class AgentContext(ToolActions, Protocol):
    @property
    def tools(self) -> ToolCaller: ...

    sandbox: SandboxAccess | None

    def read_file(self, identifier: str) -> bytes: ...
    def list_sources(self) -> list[dict]: ...
    def save_source(self, name: str, data: bytes) -> dict: ...
    def save_output(self, name: str, data: bytes) -> dict: ...
    def read_skill_blob(self, content_hash: str) -> bytes: ...
    def knowledge_call(self, name: str, arguments: dict) -> KnowledgeResult: ...
    async def web_call(self, invocation: ToolInvocation) -> ToolOutcome: ...
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


@dataclass(frozen=True)
class AgentConfig:
    recursion_limit: int = 64  # 图步数上限，不等于模型或工具调用次数。
    max_output_tokens: int = 4096  # 每次模型调用的输出 token 上限。
    context_bytes: int = 131072  # 按序列化字节限制输入，不是 token 数。
    summary_trigger_tokens: int = 16384  # 以估算 token 数触发摘要。
    summary_keep_tokens: int = 4096  # 摘要后保留的近期消息 token 预算。

    def __post_init__(self) -> None:
        validate_positive(self)
        if self.summary_keep_tokens >= self.summary_trigger_tokens:
            raise ValueError("summary_keep_tokens must be less than summary_trigger_tokens")


class CheckpointReader(Protocol):
    def for_run(self, run_id: str, reference: str | None, *, thread_id: str) -> str | None: ...
