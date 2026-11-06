"""让模型结合对话消息和员工技能回答用户的问题。
模型需要技能时，LangChain 会读取技能，再让模型继续回答。
生成中的文字和思考通过 context.report_content 记录；完整回答和累计用量返回 RunTask，由 RunService 保存成果及终态。
"""

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
)
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.types import Overwrite, StateSnapshot

from app.execution.contracts import (
    AgentContext,
    AgentOutput,
    AgentRequest,
    AgentRuntimeContext,
    RuntimeFailure,
)
from app.execution.runtime.checkpoints import (
    checkpoint_config,
)
from app.execution.runtime.concurrency import run_sync
from app.execution.runtime.model_calls import (
    ModelExecutionMiddleware,
    ReferenceContextMiddleware,
    RunUsage,
    create_summarization_middleware,
)
from app.execution.runtime.skills import (
    PreparedSkills,
    SkillLoadingMiddleware,
    build_skill_discovery_middleware,
    prepare_skills,
)
from app.execution.runtime.streaming import RunProgress, _consume_agent_stream
from app.execution.runtime.tool_calls import (
    ToolExecutionMiddleware,
    prepare_agent_tools,
    presearch,
    verify_tool_reads,
)
from app.execution.runtime.workspace import WorkspaceBackend
from app.llm.errors import classify_error
from app.llm.factory import model_session


async def execute_agent(input: AgentRequest, context: AgentContext, *, checkpoints) -> AgentOutput:
    """准备模型和技能，执行本次对话并返回回答正文及累计用量。

    input 提供提交时确定的消息和配置，context 用来记录执行过程，并检查取消和权限变化。
    没有得到完整回答，或运行已被取消、权限已失效时，抛出异常，由调用方处理。
    """
    snapshot = input.snapshot
    # 中间件检查的内容必须与下面传给 Agent 的技能文件一致，因此在这里准备一次。
    prepared_skills = prepare_skills(
        snapshot["skills"],
        snapshot["selected_skill_ids"],
    )
    progress = RunProgress(
        snapshot["max_output_bytes"], snapshot["max_reasoning_bytes"], input.recovered_content
    )

    backend = WorkspaceBackend(snapshot, prepared_skills, context)
    knowledge_context = await presearch(snapshot, context, input.messages[-1]["content"])

    async with (
        checkpoints.writer(context.checkpoint_saved) as saver,
        model_session(input.config, max_tokens=snapshot["max_output_tokens"]) as model,
    ):
        run_usage = RunUsage(input.recovered_usage)
        references = ReferenceContextMiddleware(input, context, knowledge_context)
        # 顺序决定授权、预算和技能激活的先后，在执行入口明确组装。
        middleware: list[AgentMiddleware] = [
            create_summarization_middleware(model, snapshot, context, run_usage),
            *build_skill_discovery_middleware(backend, snapshot, prepared_skills),
            ModelCallLimitMiddleware(run_limit=snapshot["max_model_calls"], exit_behavior="error"),
            ToolExecutionMiddleware(snapshot, prepared_skills, input.run_id),
            SkillLoadingMiddleware(prepared_skills, context, input.activated_skills),
            references,
            ModelExecutionMiddleware(input, context, progress, usage=run_usage),
        ]
        tools = prepare_agent_tools(snapshot, middleware)

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
                message.id for message in base.values.get("messages", []) if message.id is not None
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
                # 发布及恢复都使用完整已落盘状态，不依赖最后一个流事件是否含 model 更新。
                state = await agent.aget_state(checkpoint_config(thread_id))
            content, usage = _completed_response(state, input.run_id)
            # 生成期间用户可能已取消运行，或技能已被停用；返回前再检查一次。
            await context.guard()
            await verify_tool_reads(
                context, input.messages[-1]["content"], state.values.get("messages", [])
            )
            outputs = await run_sync(backend.collect_outputs, state.values)
            await context.guard()
            return AgentOutput(content, usage, {"output_files": outputs} if outputs else None)
        except (ModelCallLimitExceededError, GraphRecursionError):
            raise RuntimeFailure("agent_budget_exceeded") from None
        except Exception as error:
            if code := classify_error(error):
                raise RuntimeFailure(code) from None
            raise


def _prepare_run_input(
    input: AgentRequest, state: StateSnapshot, prepared: PreparedSkills
) -> dict | None:
    """Append the new question, or resume the same Run without resetting its work."""
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
    # Normal turns use the official message reducer. Only a new or invalidated branch replaces it.
    reset = not input.base_checkpoint_id or input.snapshot.get("memory_reset", False)
    return {
        "messages": Overwrite(messages) if reset else messages,
        "files": Overwrite(prepared.files),
        "pinned_skills": Overwrite(prepared.pinned_names),
        "skills_metadata": None,
        "model_usage": {},
        "app_run_id": input.run_id,
        "completed_run_id": "",
        "memory_scope": input.snapshot["memory_scope"],
    }


def _completed_response(state: StateSnapshot, run_id: str) -> tuple[str, dict | None]:
    """只从完整已落盘状态中读取属于本 Run 的最终回答及累计用量。"""
    if state.values.get("completed_run_id") != run_id or state.next:
        raise RuntimeFailure("runtime_interrupted")
    final = state.values.get("messages", [None])[-1]
    # 流结束也可能只留下工具请求，不能把它当成回答交付。
    if not isinstance(final, AIMessage) or final.tool_calls or not final.text.strip():
        raise RuntimeFailure("empty_response")
    return str(final.text), state.values.get("model_usage")
