"""Injected resource operations; no business stores or identities enter the Agent."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.tools.contracts import ToolCaller, ToolOutcome


class SandboxAccess(Protocol):
    def acquire(self) -> object: ...
    def release(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RuntimeResources:
    tools: ToolCaller
    read_file: Callable[[str], bytes]
    list_sources: Callable[[], list[dict]]
    save_source: Callable[[str, bytes], dict]
    save_output: Callable[[str, bytes], dict]
    sandbox: SandboxAccess | None = None
    read_skill_blob: Callable[[str], bytes] | None = None
    knowledge_call: Callable[[str, dict], ToolOutcome] | None = None
    knowledge_finalize: Callable[[str], str] | None = None
