"""Plain data and limited host operations shared by Agent implementations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite
from typing import Literal, NotRequired, Protocol, TypedDict, cast

from app.llm.config import LLMConfig
from app.skills.contracts import SkillExecutionEntry
from app.tools.contracts import ToolInvocation, ToolOutcome, ToolPermit


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
    skills: list[SkillExecutionEntry]
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
    context_pair_count: NotRequired[int]
    context_truncated: NotRequired[bool]
    knowledge: NotRequired[dict]


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
    config: LLMConfig
    checkpoint_id: str | None = None
    recovered_usage: dict | None = None
    activated_skills: frozenset[str] = frozenset()
    recovered_content: tuple[ContentUpdate, ...] = ()

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


class RuntimeControl(Protocol):
    async def guard(self, extra: Iterable[str] = ()) -> None: ...
    async def start_model(self) -> tuple[int, str]: ...
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


class RuntimeFailure(Exception):
    def __init__(self, code: str, partial_text: str | None = None):
        self.code, self.partial_text = code, partial_text
        super().__init__(code)
