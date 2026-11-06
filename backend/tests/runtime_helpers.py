"""An AgentContext implementation with no application database or services."""

from langchain.tools import ToolRuntime

from app.execution.contracts import AgentRuntimeContext, ContentUpdate


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

    async def start_model(self):
        self.model_calls += 1
        key = f"model:{self.model_calls}"
        await self.start(key, "model_call")
        return self.model_calls, key

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
        from app.execution.contracts import ToolPermit

        await self.start(invocation.key, "tool_call")
        return ToolPermit(invocation.key, invocation.fingerprint)

    async def guard_tool(self, invocation):
        await self.guard()

    async def complete_tool(self, permit, outcome):
        await self.finish(permit.action_key, outcome.status)


def make_task(run_id, store, authorize):
    """Exercise real RunTask action gates with only their required database boundary."""
    from types import SimpleNamespace

    from app.execution.runtime.task import RunTask

    task = RunTask(
        run_id,
        None,
        store=store,
        runs=SimpleNamespace(
            authorize=lambda row, active=(), **kwargs: authorize(active, **kwargs)
        ),
        settings=None,
        agent=None,
        connections=None,
        checkpoints=None,
        tools=None,
        files=None,
        sandboxes=None,
        skills=None,
        knowledge=None,
    )

    task.row, _ = store.load(run_id)
    return task
