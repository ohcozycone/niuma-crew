from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypedDict

from app.common.values import digest
from app.resources.environments.contracts import SandboxFileOperations

RESULT_READER = "read_tool_result"


class SandboxAccess(Protocol):
    def acquire(self) -> object: ...
    def operations(self) -> SandboxFileOperations: ...
    def release(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    key: str
    binding_id: str
    name: str
    arguments: dict
    skill_id: str | None = None
    origin: Literal["model", "host_presearch"] = "model"
    model_action_key: str | None = None

    @property
    def fingerprint(self) -> str:
        return digest([self.binding_id, self.name, self.arguments, self.skill_id, self.origin])


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
    error_code: str | None = None


class ToolCaller(Protocol):
    async def aclose(self) -> None: ...

    async def call(
        self, binding: dict, arguments: dict, guard: Callable[[], Awaitable[None]]
    ) -> ToolOutcome: ...


class ModelExposure(TypedDict):
    catalog_hash: str
    exposed_tool_ids: list[str]


class ToolActions(Protocol):
    async def begin_tool(self, invocation: ToolInvocation) -> ToolPermit: ...
    async def guard_tool(self, invocation: ToolInvocation) -> None: ...
    async def complete_tool(self, permit: ToolPermit, outcome: ToolOutcome) -> None: ...


class WorkspaceHost(Protocol):
    sandbox: SandboxAccess | None

    def read_file(self, identifier: str) -> bytes: ...
    def list_sources(self) -> list[dict]: ...
    def save_output(self, name: str, data: bytes) -> dict: ...
    def read_skill_blob(self, content_hash: str) -> bytes: ...


class ToolResultHost(Protocol):
    async def preserve_tool_result(
        self, invocation: ToolInvocation, data: dict, status: str
    ) -> tuple: ...


TOOL_CATALOG_VERSION = 1


def catalog_hash(bindings: list[dict], sources: dict) -> str:
    return digest([TOOL_CATALOG_VERSION, bindings, sources])


class SnapshotDescriptors(Protocol):
    def workspace_tools(self, workspace: dict) -> list[dict]: ...
    def knowledge_bindings(self) -> list[dict]: ...
    def knowledge_instructions(self, knowledge: dict) -> str: ...
    def result_reader_binding(self) -> dict: ...
    def search_binding(self) -> dict: ...
    def compose_system_prompt(self, rules: str, agent_prompt: str, *, agent_name: str) -> str: ...
