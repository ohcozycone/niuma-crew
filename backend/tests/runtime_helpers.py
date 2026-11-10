"""供 Agent 测试使用的内存宿主，不连接业务服务。"""

from langchain.tools import ToolRuntime

from app.runtime.contracts.agent import AgentRuntimeContext
from app.runtime.contracts.content import ContentUpdate


def agent_runtime(host, run_id="run"):
    return AgentRuntimeContext(host=host, run_id=run_id)


def tool_runtime(host, call_id, run_id="run"):
    return ToolRuntime(
        state={},
        context=agent_runtime(host, run_id),
        config={},
        stream_writer=lambda _value: None,
        tool_call_id=call_id,
        store=None,
    )


class MemoryContext:
    def __init__(self):
        self.model_calls = 0
        self.actions = {}
        self.contents: list[ContentUpdate] = []
        self.references = []

    async def guard(self, extra=()):
        pass

    async def start_model(self, exposure):
        self.model_calls += 1
        key = f"model:{self.model_calls}"
        await self.start(key, "model_call", exposure)
        return self.model_calls, key

    async def remaining_model_calls(self):
        return max(0, 8 - self.model_calls)

    async def capture_evidence(self, key, direction, stage, payload):
        self.actions[key][direction] = {"capture_stage": stage, "payload": payload}

    async def start(self, key, kind, details=None, skill_id=None, *, budget=None):
        self.actions[key] = {"kind": kind, "status": "running", "budget": budget}

    async def finish(
        self, key, status="succeeded", error=None, details=None, usage=None, content=None
    ):
        self.actions[key]["status"] = status
        if content:
            self.contents.append(content)

    async def report_content(self, update):
        self.contents.append(update)

    async def checkpoint_saved(self, reference):
        self.references.append(reference)

    tools = None
    sandbox = None
    read_skill_blob = None
    knowledge_call = None
    preserve_tool_result = None
    load_tool_result = None
    read_tool_result = None
    verify_web_reads = None
    clean_history = None

    def list_sources(self):
        return []

    def save_output(self, name, data):
        raise AssertionError("No output storage was granted")

    async def begin_tool(self, invocation):
        from app.runtime.contracts.tools import ToolPermit

        await self.start(invocation.key, "tool_call")
        return ToolPermit(invocation.key, invocation.fingerprint)

    async def guard_tool(self, invocation):
        await self.guard()

    async def complete_tool(self, permit, outcome):
        await self.finish(permit.action_key, outcome.status)


def make_task(run_id, store, authorize):
    """使用真实动作账本的 Context，仅替换授权服务。"""
    from types import SimpleNamespace

    from app.execution.context import RunContext

    row, _ = store.load(run_id)
    return RunContext(
        row,
        store=store,
        runs=SimpleNamespace(
            authorize=lambda row, active=(), **kwargs: authorize(
                active, **{key: value for key, value in kwargs.items() if key != "exposure"}
            )
        ),
        files=None,
        skills=None,
        knowledge=None,
        tools=None,
        sandbox=None,
    )


def bind_model_calls(store, run_id, *invocations):
    from dataclasses import replace

    row, _ = store.load(run_id)
    names = {
        item["exposed_name"]: item["binding_id"] for item in row.config_snapshot.get("tools", [])
    }
    _, key = store.start_model(
        run_id,
        lambda db: None,
        exposure={
            "catalog_hash": row.config_snapshot["tool_catalog"]["catalog_hash"],
            "exposed_tool_ids": [names[item.name] for item in invocations],
        },
    )
    store.finish_action(
        run_id,
        key,
        details={
            "tool_call_ids": [item.key.removeprefix("tool:") for item in invocations],
            "tool_calls": [
                {"id": item.key.removeprefix("tool:"), "name": item.name} for item in invocations
            ],
        },
    )
    return tuple(replace(item, model_action_key=key) for item in invocations)
