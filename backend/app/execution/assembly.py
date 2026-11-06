"""Build the execution subsystem without starting tasks or opening resources."""

from functools import partial
from typing import Any

from app.execution.contracts import ExecutionStatus
from app.execution.runtime.agent import execute_agent
from app.execution.runtime.checkpoints import CheckpointStore
from app.execution.runtime.task import RunTask
from app.execution.runtime.worker import RunWorker
from app.execution.service import RunService
from app.execution.snapshot import RunConfiguration
from app.execution.store import RunStore


def build_execution(
    *,
    database: Any,
    runtime: Any,
    lock_file: Any,
    model_connections: Any,
    files: Any,
    skills: Any,
    knowledge: Any,
    tools: Any,
    sandboxes: Any,
) -> tuple[RunService, RunWorker]:
    """Connect application resources to the service and its lifespan-owned worker."""
    status = ExecutionStatus("starting" if runtime.enabled else "ready")
    store = RunStore(database, files=files)
    checkpoints = CheckpointStore(database.engine.url.database)
    configuration = RunConfiguration(runtime, files=files, sandboxes=sandboxes, knowledge=knowledge)

    def finalize_content(db: Any, row: Any, text: Any) -> Any:
        return (
            knowledge.evidence.finalize_answer(row.id, text, db=db)
            if row.config_snapshot.get("knowledge")
            else text
        )

    runs = RunService(
        database,
        runtime,
        status,
        configuration,
        model_connections,
        knowledge=knowledge,
        check_outputs=files.check_outputs,
        prepare_content=finalize_content,
    )
    task_factory = partial(
        RunTask,
        store=store,
        runs=runs,
        settings=runtime,
        agent=partial(execute_agent, checkpoints=checkpoints),
        connections=model_connections,
        checkpoints=checkpoints,
        tools=tools,
        files=files,
        sandboxes=sandboxes,
        skills=skills,
        knowledge=knowledge,
    )
    worker = RunWorker(
        store,
        runs,
        task_factory,
        runtime,
        status,
        lock_file,
    )
    return runs, worker
