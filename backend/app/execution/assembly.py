from functools import partial
from types import SimpleNamespace
from typing import Any

from app.agent.checkpoints import CheckpointStore
from app.agent.config import AgentConfig
from app.agent.engine import execute_agent
from app.agent.prompts import compose_system_prompt
from app.builtin_tools.knowledge import knowledge_instructions
from app.builtin_tools.knowledge import tool_bindings as knowledge_bindings
from app.builtin_tools.results import result_reader_binding
from app.builtin_tools.tool_search import search_binding
from app.builtin_tools.workspace import workspace_tools
from app.execution.runner import RunTask
from app.execution.scheduler import RunWorker
from app.execution.service import RunService
from app.execution.snapshot import RunConfiguration
from app.execution.store import RunStore
from app.runtime.contracts.runs import ExecutionStatus


def build_execution(
    *,
    database: Any,
    runtime: Any,
    agent_settings: AgentConfig = AgentConfig(),
    lock_file: Any,
    model_connections: Any,
    files: Any,
    skills: Any,
    knowledge_access: Any,
    knowledge_evidence: Any,
    knowledge_search: Any,
    tools: Any,
    sandboxes: Any,
) -> tuple[RunService, RunWorker]:
    status = ExecutionStatus("starting" if runtime.enabled else "ready")
    store = RunStore(database, files=files)
    checkpoints = CheckpointStore(database.engine.url.database)
    configuration = RunConfiguration(
        runtime,
        SimpleNamespace(
            workspace_tools=workspace_tools,
            knowledge_bindings=knowledge_bindings,
            knowledge_instructions=knowledge_instructions,
            result_reader_binding=result_reader_binding,
            search_binding=search_binding,
            compose_system_prompt=compose_system_prompt,
        ),
        agent=agent_settings,
        files=files,
        sandboxes=sandboxes,
        knowledge=knowledge_evidence,
    )

    def finalize_content(db: Any, row: Any, text: Any) -> Any:
        return (
            knowledge_evidence.finalize_answer(row.id, text, db=db)
            if row.config_snapshot.get("knowledge")
            else text
        )

    runs = RunService(
        database,
        runtime,
        status,
        configuration,
        model_connections,
        knowledge=knowledge_access,
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
        knowledge=knowledge_search,
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
