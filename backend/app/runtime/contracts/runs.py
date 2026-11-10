from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict

from app.runtime.contracts.agent import AgentSnapshot
from app.runtime.contracts.content import AgentResult, ContentUpdate


class OrganizationRulesSnapshot(TypedDict):
    instructions: str
    revision: int
    updated_at: str


class RunSpec(AgentSnapshot):
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


# 版本 8 冻结组织资源并逐请求记录工具暴露；升级前须排空旧活动 Run。
RUN_SNAPSHOT_VERSION = 8
SUPPORTED_SNAPSHOT_VERSIONS = frozenset({RUN_SNAPSHOT_VERSION})


def run_thread_id(origin: str, identifier: str, *, snapshot_version: int | None = None) -> str:
    version = RUN_SNAPSHOT_VERSION if snapshot_version is None else snapshot_version
    # 版本 8 起分隔 SDK 线程；更早正式历史仍保留原线程标识。
    return f"{origin}:v{version}:{identifier}" if version >= 8 else f"{origin}:{identifier}"


@dataclass(frozen=True, slots=True)
class RunState:
    id: str
    created_at: datetime
    updated_at: datetime
    agent_id: str
    owner_user_id: str
    initiated_by_user_id: str
    initiated_by_session_id: str | None
    origin_kind: str
    operation: str
    trigger: str
    mode: str
    client_request_id: str
    request_hash: str
    retry_of_run_id: str | None
    model_connection_id: str | None
    config_snapshot: dict
    input_snapshot: list
    thread_id: str
    base_checkpoint_id: str | None
    base_run_id: str | None
    checkpoint_id: str | None
    result_text: str | None
    result_data: dict | None
    status: str
    revision: int
    actions_revision: int
    model_calls: int
    skill_reads: int
    tool_calls: int
    error_code: str | None
    usage: dict | None
    started_at: datetime | None
    cancel_requested_at: datetime | None
    finished_at: datetime | None


ACTIVE = ("queued", "running", "cancelling")
TERMINAL = ("succeeded", "failed", "cancelled", "interrupted")
