"""Plain data and limited host operations shared by Agent implementations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from math import isfinite
from typing import Literal, NotRequired, Protocol, TypedDict, cast

from app.values import digest


class InputMessage(TypedDict):
    id: str
    role: Literal["user", "assistant"]
    content: str


class AgentSnapshot(TypedDict):
    """Frozen execution input; optional resource fields support pre-tool snapshots."""

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
    tool_user_id: NotRequired[str | None]
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


def validate_snapshot(value: dict) -> AgentSnapshot:
    """Reject unreadable stored inputs before resolving credentials or calling a model."""
    valid = all(
        isinstance(value.get(key), str) for key in ("agent_id", "connection_id", "system_prompt")
    ) and all(
        type(value.get(key)) is int and value[key] > 0
        for key in (
            "schema_version",
            "connection_config_revision",
            "connection_credential_revision",
            "recursion_limit",
            "max_model_calls",
            "max_skill_reads",
            "max_output_tokens",
            "max_output_bytes",
            "max_reasoning_bytes",
            "context_bytes",
        )
    )
    if value.get("schema_version") == 4 and (
        any(
            type(value.get(key)) is not int or value[key] <= 0
            for key in ("summary_trigger_tokens", "summary_keep_tokens")
        )
        or value.get("summary_keep_tokens", 0) >= value.get("summary_trigger_tokens", 0)
        or not isinstance(value.get("memory_scope"), str)
        or not isinstance(value.get("memory_reset"), bool)
    ):
        raise RuntimeFailure("checkpoint_unavailable")
    skills = value.get("skills")
    selected = value.get("selected_skill_ids")
    if not valid or not isinstance(skills, list) or not isinstance(selected, list):
        raise RuntimeFailure("checkpoint_unavailable")
    if not all(isinstance(item, str) for item in selected):
        raise RuntimeFailure("checkpoint_unavailable")
    for skill in skills:
        if (
            not isinstance(skill, dict)
            or not all(
                isinstance(skill.get(key), str)
                for key in (
                    "skill_id",
                    "name",
                    "description",
                    "instructions",
                    "instructions_hash",
                    "assignment_created_at",
                )
            )
            or not all(
                type(skill.get(key)) is int and skill[key] > 0
                for key in ("skill_revision", "assignment_revision")
            )
            or not isinstance(skill.get("parameters"), dict)
        ):
            raise RuntimeFailure("checkpoint_unavailable")
    if (
        type(value.get("run_timeout")) not in (int, float)
        or not isfinite(value["run_timeout"])
        or value["run_timeout"] <= 0
    ):
        raise RuntimeFailure("checkpoint_unavailable")
    return cast(AgentSnapshot, value)


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


class AgentContext(Protocol):
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
    def read_tool_result(self, result_id: str, offset: int = 0, limit: int = 6000) -> str: ...
    def verify_web_reads(self, content: str, observations: list) -> None: ...
    def clean_history(self, content: str) -> str: ...

    async def guard(self, extra: Iterable[str] = ()) -> None: ...
    async def start_model(self) -> tuple[int, str]: ...
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
    async def begin_tool(self, invocation: ToolInvocation) -> ToolPermit: ...
    async def guard_tool(self, invocation: ToolInvocation) -> None: ...
    async def complete_tool(self, permit: ToolPermit, outcome: ToolOutcome) -> None: ...


class AgentRuntimeContext(TypedDict):
    """Trusted per-run input carried by the framework, outside model tool arguments."""

    host: AgentContext
    run_id: str


class RuntimeFailure(Exception):
    def __init__(self, code: str, partial_text: str | None = None):
        self.code, self.partial_text = code, partial_text
        super().__init__(code)


RUN_SNAPSHOT_VERSION = 5

SUPPORTED_SNAPSHOT_VERSIONS = frozenset({RUN_SNAPSHOT_VERSION})

RESULT_READER = "read_tool_result"


@dataclass(frozen=True, slots=True)
class ToolReadObservation:
    result_id: str
    start: int
    end: int


class OrganizationRulesSnapshot(TypedDict):
    instructions: str
    revision: int
    updated_at: str


class RunSpec(AgentSnapshot):
    """Accepted runtime input uses the same plain contract as the Agent boundary."""

    checkpoint_resumable: bool
    allow_partial_output: bool
    agent_revision: int
    authorized_skill_ids: list[str]
    agent_name: str
    agent_updated_at: str
    agent_system_prompt: str
    organization_rules: OrganizationRulesSnapshot
    connection_name: str
    preset_id: str
    provider: str
    protocol: str
    base_url: str
    model_id: str


@dataclass(slots=True)
class ExecutionStatus:
    phase: Literal["starting", "ready", "degraded", "stopping", "failed"] = "starting"

    @property
    def accepting(self) -> bool:
        return self.phase == "ready"


@dataclass(frozen=True, slots=True)
class Completion:
    run_id: str
    content: str | None
    status: str
    error: str | None = None
    usage: dict | None = None
    structured: AgentResult | None = None
    progress: tuple[ContentUpdate, ...] = ()


class SandboxAccess(Protocol):
    def acquire(self) -> object: ...
    def release(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    key: str
    binding_id: str
    name: str
    arguments: dict
    skill_id: str | None = None

    @property
    def fingerprint(self) -> str:
        return digest([self.binding_id, self.name, self.arguments, self.skill_id])


@dataclass(frozen=True, slots=True)
class ToolPermit:
    action_key: str
    fingerprint: str
    cached: dict | None = None


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    content: str
    status: str = "succeeded"
    data: dict = field(default_factory=dict)
    sources: tuple[dict, ...] = ()


class ToolCaller(Protocol):
    async def aclose(self) -> None: ...

    async def call(
        self, binding: dict, arguments: dict, guard: Callable[[], Awaitable[None]]
    ) -> ToolOutcome: ...
