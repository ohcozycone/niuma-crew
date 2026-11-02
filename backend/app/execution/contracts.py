"""Small boundaries between scheduling, execution and SDK adaptation."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from app.agent_runtime.contracts import (
    AgentOutput,
    AgentResult,
    AgentSnapshot,
    ContentUpdate,
    RuntimeControl,
)

# 快照协议版本，不是可由部署环境调整的运行参数。
RUN_SNAPSHOT_VERSION = 3
SUPPORTED_SNAPSHOT_VERSIONS = frozenset({2, 3})


class RunSpec(AgentSnapshot):
    """Accepted runtime input uses the same plain contract as the Agent boundary."""


@dataclass(frozen=True, slots=True)
class ExecutionStrategy:
    execute: Callable[[RuntimeControl], Awaitable[AgentOutput]]
    publish_partial: bool = True


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
