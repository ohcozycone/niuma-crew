from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


class InputMessage(TypedDict):
    id: str
    role: Literal["user", "assistant"]
    content: str


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
class ContentUpdate:
    key: str
    output_text: str
    reasoning_text: str
    reasoning_truncated: bool
    has_tool_calls: bool
