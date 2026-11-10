from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langchain_core.tools import BaseTool

from app.runtime.contracts.tools import ToolInvocation, ToolOutcome, ToolResultHost


@dataclass(frozen=True, slots=True)
class ToolBinding:
    tool: BaseTool | None
    normalize: Callable[[object, ToolInvocation, ToolResultHost], Awaitable[ToolOutcome]]
    render_saved: Callable[[dict, str], object] | None = None
