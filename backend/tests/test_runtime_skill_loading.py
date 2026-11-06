"""工作区操作共用一个执行锁，技能激活事实在运行内只保存一份。"""

import asyncio
from types import SimpleNamespace

from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt.tool_node import ToolCallRequest
from runtime_helpers import MemoryContext, tool_runtime

from app.execution.runtime.skills import SkillLoadingMiddleware, prepare_skills
from app.execution.runtime.tool_calls import ToolExecutionMiddleware


def test_unrelated_tools_can_run_in_parallel_through_skill_loading():
    async def scenario():
        middleware = SkillLoadingMiddleware(prepare_skills([], []), MemoryContext())
        both_started = asyncio.Event()
        started = 0

        async def handler(request):
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=1)
            return ToolMessage(content="完成", tool_call_id=request.tool_call["id"])

        requests = [
            SimpleNamespace(tool_call={"name": "external_tool", "id": str(index), "args": {}})
            for index in range(2)
        ]
        await asyncio.gather(
            *(middleware.awrap_tool_call(request, handler) for request in requests)
        )
        assert started == 2

    asyncio.run(scenario())


def test_parallel_reads_activate_once_and_share_the_prepared_skill_state():
    async def scenario():
        skill = {
            "skill_id": "skill",
            "name": "技能",
            "description": "加载测试",
            "instructions": "完整正文",
            "parameters": {},
            "skill_revision": 1,
            "assignment_revision": 1,
            "instructions_hash": "frozen",
        }
        prepared = prepare_skills([skill], [])
        context = MemoryContext()
        middleware = SkillLoadingMiddleware(prepared, context)
        execution = ToolExecutionMiddleware({}, prepared, "run")
        activations = []
        start = context.start

        async def record_start(key, kind, *args, **kwargs):
            activations.append(kind)
            await start(key, kind, *args, **kwargs)

        context.start = record_start

        async def handler(request):
            await asyncio.sleep(0)
            assert request.tool_call["args"]["offset"] == 0
            assert request.tool_call["args"]["limit"] == 1000000
            return ToolMessage(content="完整正文", tool_call_id=request.tool_call["id"])

        def read_file(file_path: str, offset: int = 0, limit: int = 2000) -> str:
            """读取技能正文。"""
            return "完整正文"

        tool = StructuredTool.from_function(read_file)

        def request(index):
            return ToolCallRequest(
                tool=tool,
                tool_call={
                    "name": "read_file",
                    "id": str(index),
                    "args": {"file_path": "/skills/s-skill/SKILL.md", "offset": 10, "limit": 1},
                },
                state={},
                runtime=tool_runtime(context, str(index)),
            )

        async def load(request):
            return await middleware.awrap_tool_call(request, handler)

        await asyncio.gather(
            execution.awrap_tool_call(request(1), load),
            execution.awrap_tool_call(request(2), load),
        )
        assert activations.count("skill_activation") == 1
        assert activations.count("tool_call") == 2
        assert prepared.active_skill_ids == {"skill"}
        assert context.actions["skill:skill"]["status"] == "succeeded"

    asyncio.run(scenario())
