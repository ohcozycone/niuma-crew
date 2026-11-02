"""Plain tool contracts shared with the runtime and execution host."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Protocol


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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
    async def call(self, binding: dict, arguments: dict, guard) -> ToolOutcome: ...


FILE_TOOLS = ("ls", "read_file", "glob", "grep", "write_file", "edit_file", "delete")
WRITE_TOOLS = frozenset({"write_file", "edit_file", "delete", "execute"})
RESERVED_NAMES = frozenset((*FILE_TOOLS, "execute", "read_tool_result"))


def native_catalog(mode: str) -> list[dict]:
    names = [*FILE_TOOLS, *(["execute"] if mode == "sandbox" else [])]
    return [
        {
            "name": name,
            "description": f"平台受控工作区：{name}",
            "input_schema": {"type": "object"},
            "recovery": "never" if name in WRITE_TOOLS else "readonly",
            "descriptor_hash": digest(["workspace-v1", mode, name]),
        }
        for name in names
    ]


def exposed_name(connection_id: str, name: str) -> str:
    # Stable and bounded even when two servers export the same tool name.
    return (
        "mcp_"
        + connection_id.replace("-", "")
        + "_"
        + hashlib.sha256(name.encode()).hexdigest()[:16]
    )
