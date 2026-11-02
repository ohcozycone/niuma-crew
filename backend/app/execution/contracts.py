"""Small boundaries between scheduling, execution and SDK adaptation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypedDict

from app.agent_runtime.contracts import (
    AgentOutput,
    AgentResult,
    AgentSnapshot,
    ContentUpdate,
)

if TYPE_CHECKING:
    from app.execution.control import RunControl

# 快照协议版本，不是可由部署环境调整的运行参数。
RUN_SNAPSHOT_VERSION = 3
SUPPORTED_SNAPSHOT_VERSIONS = frozenset({2, 3})


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
    context_pairs: int


@dataclass(frozen=True, slots=True)
class ExecutionStrategy:
    execute: Callable[[RunControl], Awaitable[AgentOutput]]
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
