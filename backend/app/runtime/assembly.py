from functools import partial
from types import SimpleNamespace
from typing import Any

from app.runtime.agent.checkpoints import CheckpointStore
from app.runtime.agent.config import AgentConfig
from app.runtime.agent.engine import execute_agent
from app.runtime.agent.prompts import compose_system_prompt
from app.runtime.contracts.runs import ExecutionStatus
from app.runtime.execution.runner import RunTask
from app.runtime.execution.scheduler import RunWorker
from app.runtime.execution.service import RunService
from app.runtime.execution.snapshot import RunConfiguration
from app.runtime.execution.store import RunStore
from app.runtime.tools.knowledge import knowledge_instructions
from app.runtime.tools.knowledge import tool_bindings as knowledge_bindings
from app.runtime.tools.results import result_reader_binding
from app.runtime.tools.tool_search import search_binding
from app.runtime.tools.web import WebService, web_bindings
from app.runtime.tools.web_config import WebConfig
from app.runtime.tools.workspace import workspace_tools


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
    web_config: WebConfig = WebConfig(),
) -> tuple[RunService, RunWorker]:
    status = ExecutionStatus("starting" if runtime.enabled else "ready")
    store = RunStore(database, files=files)
    checkpoints = CheckpointStore(database.engine.url.database)
    configuration = RunConfiguration(
        runtime,
        SimpleNamespace(
            workspace_tools=workspace_tools,
            web_bindings=web_bindings,
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
        web_ready=web_config.ready,
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
        web=WebService(web_config),
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
