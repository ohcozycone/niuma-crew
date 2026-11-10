from __future__ import annotations

from typing import Any, Protocol, cast

from app.execution.context import RunContext
from app.execution.errors import ExecutionFailure
from app.execution.snapshot_rules import validate_snapshot
from app.runtime.contracts.agent import AgentRequest, AgentSnapshot
from app.runtime.contracts.runs import SUPPORTED_SNAPSHOT_VERSIONS


class PreparationHost(Protocol):
    run_id: str
    row: Any
    _store: Any
    _checkpoints: Any
    _connections: Any
    _tool_service: Any
    _sandboxes: Any
    _files: Any
    _skills: Any
    _knowledge: Any
    _runs: Any
    _tools: Any
    sandbox: Any
    context: Any
    request: Any


def prepare_run(host: PreparationHost) -> None:
    if host.row is None:
        host.row, _ = host._store.load(host.run_id)
    row = host.row
    if row.config_snapshot.get("schema_version") not in SUPPORTED_SNAPSHOT_VERSIONS:
        raise ExecutionFailure("checkpoint_unavailable")
    checkpoint = host._checkpoints.for_run(row.id, row.checkpoint_id, thread_id=row.thread_id)
    if row.model_calls and checkpoint is None:
        raise ExecutionFailure("checkpoint_unavailable")
    snapshot = cast(AgentSnapshot, dict(validate_snapshot(row.config_snapshot)))
    config = host._connections.resolve(
        snapshot["connection_id"],
        snapshot["connection_config_revision"],
        snapshot["connection_credential_revision"],
    )
    host._tools = host._tool_service.for_run(row.id)
    if snapshot.get("workspace", {}).get("mode") == "sandbox":
        host.sandbox = host._sandboxes.for_run(
            row.id,
            snapshot.get("input_files", []),
            host._files.read,
            profile=snapshot["workspace"],
        )
    host.context = RunContext(
        row,
        store=host._store,
        runs=host._runs,
        files=host._files,
        skills=host._skills,
        knowledge=host._knowledge,
        tools=host._tools,
        sandbox=host.sandbox,
    )
    host.context.restore(host._store.restore_control(row.id))
    host.request = AgentRequest(
        row.id,
        snapshot,
        row.input_snapshot,
        config,
        checkpoint,
        recovered_usage=host.context.recovered_usage,
        activated_skills=frozenset(host.context.active_skills),
        recovered_content=tuple(host.context.progress.contents.values()),
        thread_id=row.thread_id,
        base_checkpoint_id=row.base_checkpoint_id,
        base_run_id=row.base_run_id,
    )
