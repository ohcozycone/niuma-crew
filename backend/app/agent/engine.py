from contextlib import closing

from deepagents.backends import CompositeBackend
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.types import Overwrite, StateSnapshot

from app.agent.checkpoints import (
    checkpoint_config,
)
from app.agent.errors import RuntimeFailure
from app.agent.model_calls import (
    ModelExecutionMiddleware,
    ReferenceContextMiddleware,
    RunUsage,
    create_summarization_middleware,
)
from app.agent.skills import (
    PreparedSkills,
    SkillLoadingMiddleware,
    build_skill_discovery_middleware,
    prepare_skills,
)
from app.agent.streaming import RunProgress, _consume_agent_stream
from app.agent.tool_calls import (
    ToolExecutionMiddleware,
    prepare_agent_tools,
    presearch,
)
from app.agent.tool_discovery import ToolDiscovery
from app.builtin_tools.result_files import RESULT_FILES_ROOT, ToolResultBackend
from app.builtin_tools.workspace import WorkspaceBackend, filesystem_middleware
from app.infrastructure.concurrency import run_sync
from app.llm.errors import classify_error
from app.llm.factory import model_session
from app.runtime.contracts.agent import AgentContext, AgentOutput, AgentRequest, AgentRuntimeContext


async def execute_agent(input: AgentRequest, context: AgentContext, *, checkpoints) -> AgentOutput:
    """返回完整回答与用量；失败和取消交由宿主处理。"""
    snapshot = input.snapshot
    with closing(ToolDiscovery(snapshot)) as discovery:
        # 中间件与文件后端共用同一份技能数据。
        prepared_skills = prepare_skills(
            snapshot["skills"],
            snapshot["selected_skill_ids"],
        )
        progress = RunProgress(
            snapshot["max_output_bytes"], snapshot["max_reasoning_bytes"], input.recovered_content
        )

        result_backend = ToolResultBackend(context)
        backend = WorkspaceBackend(
            snapshot, prepared_skills, context, result_sources=result_backend.sources
        )
        knowledge_context = await presearch(snapshot, context, input.messages[-1]["content"])

        async with (
            checkpoints.writer(context.checkpoint_saved) as saver,
            model_session(input.config, max_tokens=snapshot["max_output_tokens"]) as model,
        ):
            run_usage = RunUsage(input.recovered_usage)
            references = ReferenceContextMiddleware(input, context, knowledge_context)
            tool_execution = ToolExecutionMiddleware(snapshot, prepared_skills, input.run_id)
            # 顺序保证先检查授权和预算，再激活技能。
            middleware: list[AgentMiddleware] = [
                create_summarization_middleware(model, snapshot, context, run_usage),
                *build_skill_discovery_middleware(backend, snapshot, prepared_skills),
                tool_execution,
                SkillLoadingMiddleware(prepared_skills, context, input.activated_skills),
                references,
                discovery,
                ModelExecutionMiddleware(input, context, progress, usage=run_usage),
            ]
            names = [
                item["tool_name"]
                for item in snapshot.get("tools", [])
                if item["kind"] == "workspace"
            ]
            if names:
                filesystem = filesystem_middleware(
                    CompositeBackend(
                        default=backend,
                        routes={RESULT_FILES_ROOT + "/": result_backend},
                        artifacts_root="/sources",
                    ),
                    names,
                    context_bytes=snapshot["context_bytes"],
                )
                middleware.insert(middleware.index(tool_execution) + 1, filesystem)
            tools, tool_execution.adapters = prepare_agent_tools(
                snapshot, middleware, context, discovery
            )

            agent = create_agent(
                model=model,
                tools=tools,
                middleware=middleware,
                system_prompt=snapshot["system_prompt"],
                checkpointer=saver,
                context_schema=AgentRuntimeContext,
            )

            thread_id = input.thread_id
            config = checkpoint_config(
                thread_id, input.checkpoint_id or input.base_checkpoint_id, input.run_id
            )
            config["recursion_limit"] = snapshot["recursion_limit"]
            state = await agent.aget_state(config)
            if input.base_checkpoint_id:
                base = (
                    await agent.aget_state(checkpoint_config(thread_id, input.base_checkpoint_id))
                    if input.checkpoint_id
                    else state
                )
                references.history_ids = {
                    message.id
                    for message in base.values.get("messages", [])
                    if message.id is not None
                }
            value = _prepare_run_input(input, state, prepared_skills)

            try:
                if value is not None or state.next:
                    stream = agent.astream(
                        value,
                        config,
                        context=AgentRuntimeContext(host=context, run_id=input.run_id),
                        stream_mode=["messages"],
                        version="v2",
                        durability="sync",
                    )
                    await _consume_agent_stream(stream, context, progress)
                    # 最终成果以完整存档为准，末尾流事件不一定含完整状态。
                    state = await agent.aget_state(checkpoint_config(thread_id))
                content, usage = _completed_response(state, input.run_id)
                # 返回前复核取消和撤权，避免迟到成果被接纳。
                await context.guard()
                outputs = await run_sync(backend.collect_outputs, state.values)
                await context.guard()
                return AgentOutput(content, usage, {"output_files": outputs} if outputs else None)
            except GraphRecursionError:
                raise RuntimeFailure("agent_budget_exceeded") from None
            except Exception as error:
                if code := classify_error(error):
                    raise RuntimeFailure(code) from None
                raise


def _prepare_run_input(
    input: AgentRequest, state: StateSnapshot, prepared: PreparedSkills
) -> dict | None:
    """新一轮追加问题；同 Run 恢复不重置已有工作。"""
    values = state.values
    if input.checkpoint_id:
        if values.get("app_run_id") != input.run_id:
            raise RuntimeFailure("checkpoint_unavailable")
        return None
    if input.base_checkpoint_id and (
        values.get("app_run_id") != input.base_run_id
        or values.get("completed_run_id") != input.base_run_id
    ):
        raise RuntimeFailure("checkpoint_unavailable")
    messages = [
        (HumanMessage if item["role"] == "user" else AIMessage)(
            id=item["id"], content=item["content"]
        )
        for item in input.messages
    ]
    # 普通续轮追加消息，仅新建或失效分支替换状态。
    reset = not input.base_checkpoint_id or input.snapshot.get("memory_reset", False)
    return {
        "messages": Overwrite(messages) if reset else messages,
        "files": Overwrite(prepared.files),
        "discovered_tool_ids": Overwrite([]),
        "pinned_skills": Overwrite(prepared.pinned_names),
        "skills_metadata": None,
        "model_usage": {},
        "app_run_id": input.run_id,
        "completed_run_id": "",
        "memory_scope": input.snapshot["memory_scope"],
    }


def _completed_response(state: StateSnapshot, run_id: str) -> tuple[str, dict | None]:
    """仅读取完整存档中属于本 Run 的最终回答。"""
    if state.values.get("completed_run_id") != run_id or state.next:
        raise RuntimeFailure("runtime_interrupted")
    final = state.values.get("messages", [None])[-1]
    # 流结束仍可能停在工具请求，不能当作最终回答。
    if not isinstance(final, AIMessage) or final.tool_calls or not final.text.strip():
        raise RuntimeFailure("empty_response")
    return str(final.text), state.values.get("model_usage")
