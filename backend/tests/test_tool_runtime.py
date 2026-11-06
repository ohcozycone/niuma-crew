"""Official runtime injection, per-call isolation and the platform action boundary."""

import asyncio
import json
from threading import Barrier, Event
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolCallRequest
from runtime_helpers import MemoryContext, agent_runtime, tool_runtime

from app.execution.contracts import AgentRuntimeContext, RuntimeFailure, ToolOutcome
from app.execution.runtime.skills import prepare_skills
from app.execution.runtime.tool_calls import ToolExecutionMiddleware, prepare_agent_tools


def binding(kind="mcp_http", name="lookup"):
    return {
        "kind": kind,
        "binding_id": "binding:" + name,
        "exposed_name": name,
        "description": "查询",
        "tool_name": name,
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "runtime": {}},
            "required": ["query"],
            "additionalProperties": False,
        },
    }


def message(*calls):
    return {"messages": [AIMessage(content="", tool_calls=list(calls))]}


def call(identifier, query, name="lookup", **extra):
    return {"name": name, "id": identifier, "args": {"query": query, **extra}}


def tool_graph(bindings, run_id="run", *, tools=None, saver=None, interrupt_before=None):
    snapshot = {"tools": bindings}
    tools = prepare_agent_tools(snapshot, []) if tools is None else tools
    middleware = ToolExecutionMiddleware(snapshot, prepare_skills([], []), run_id)
    builder = StateGraph(MessagesState, context_schema=AgentRuntimeContext)
    builder.add_node(
        "tools",
        ToolNode(tools, awrap_tool_call=middleware.awrap_tool_call, handle_tool_errors=False),
    )
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    return builder.compile(checkpointer=saver, interrupt_before=interrupt_before), tools


class TraceHost(MemoryContext):
    def __init__(self, name="host"):
        super().__init__()
        self.name, self.events, self.invocations, self.received = name, [], {}, []
        self.tools = SimpleNamespace(call=self.mcp_call)
        self.before_return = None
        self.denied = False
        self.fail_save = False

    async def begin_tool(self, invocation):
        self.events.append(("authorize", invocation.key))
        if self.denied:
            raise RuntimeFailure("permission_denied")
        self.invocations[invocation.key] = invocation
        permit = await super().begin_tool(invocation)
        self.events.append(("started", invocation.key))
        return permit

    async def guard_tool(self, invocation):
        self.events.append(("guard", invocation.key))
        assert self.invocations[invocation.key].fingerprint == invocation.fingerprint
        if self.denied:
            raise RuntimeFailure("permission_denied")

    async def mcp_call(self, bound, arguments, guard):
        await guard()
        self.received.append((bound["binding_id"], arguments.copy()))
        self.events.append(("transport", arguments["query"]))
        if self.before_return:
            await self.before_return(arguments)
        await guard()
        return ToolOutcome("结果", data={"host": self.name, **arguments})

    async def preserve_tool_result(self, invocation, data, status):
        self.events.append(("preserve", invocation.key))
        assert invocation.arguments["query"] == data["query"]
        assert data["host"] == self.name
        return json.dumps(data), {"file_id": self.name + invocation.key}, ()

    async def complete_tool(self, permit, outcome):
        assert permit.fingerprint == self.invocations[permit.action_key].fingerprint
        self.events.append(("save", permit.action_key))
        if self.fail_save:
            raise RuntimeError("save failed")
        await super().complete_tool(permit, outcome)

    def read_tool_result(self, result_id, offset=0, limit=6000):
        return json.dumps(
            {"host": self.name, "result_id": result_id, "offset": offset, "limit": limit}
        )


def test_parallel_mcp_calls_keep_ids_arguments_permits_and_remote_runtime_separate():
    async def scenario():
        host = TraceHost()
        graph, tools = tool_graph([binding()])
        both_started = asyncio.Event()

        async def overlap(arguments):
            if len(host.received) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=2)
            if arguments["query"] == "first":
                await asyncio.sleep(0.01)

        host.before_return = overlap
        output = await graph.ainvoke(
            message(
                call("one", "first", runtime={"remote": 1}), call("two", "second", runtime="远端")
            ),
            context=agent_runtime(host),
        )
        results = {item.tool_call_id: json.loads(item.content) for item in output["messages"][1:]}
        assert results == {
            "one": {"host": "host", "query": "first", "runtime": {"remote": 1}},
            "two": {"host": "host", "query": "second", "runtime": "远端"},
        }
        assert all(row["status"] == "succeeded" for row in host.actions.values())
        assert {key: value.arguments for key, value in host.invocations.items()} == {
            "tool:one": {"query": "first", "runtime": {"remote": 1}},
            "tool:two": {"query": "second", "runtime": "远端"},
        }
        assert tools[0].coroutine is None  # Only the per-request copy is bound.
        assert tools[0].args_schema == binding()["input_schema"]
        assert tools[0].tool_call_schema["properties"] == binding()["input_schema"]["properties"]
        assert set(agent_runtime(host)) == {"host", "run_id"}

    asyncio.run(scenario())


def test_concurrent_runs_can_share_registered_tools_without_sharing_host():
    async def scenario():
        bindings = [binding()]
        tools = prepare_agent_tools({"tools": bindings}, [])
        first, _ = tool_graph(bindings, "first-run", tools=tools)
        second, _ = tool_graph(bindings, "second-run", tools=tools)
        hosts = [TraceHost("first-host"), TraceHost("second-host")]
        outputs = await asyncio.gather(
            first.ainvoke(
                message(call("same-id", "first")), context=agent_runtime(hosts[0], "first-run")
            ),
            second.ainvoke(
                message(call("same-id", "second")), context=agent_runtime(hosts[1], "second-run")
            ),
        )
        for index, output in enumerate(outputs):
            data = json.loads(output["messages"][-1].content)
            assert data["host"] == hosts[index].name
            assert hosts[index].invocations["tool:same-id"].arguments == {"query": data["query"]}
            assert hosts[index].actions["tool:same-id"]["status"] == "succeeded"
        assert tools[0].coroutine is None

    asyncio.run(scenario())


def test_parallel_knowledge_tools_receive_their_own_framework_call_id():
    async def scenario():
        host = TraceHost()
        rendezvous = Barrier(2, timeout=2)

        def knowledge(name, arguments):
            rendezvous.wait()
            return ToolOutcome(arguments["query"])

        host.knowledge_call = knowledge
        graph, _ = tool_graph([binding("knowledge")])
        output = await graph.ainvoke(
            message(call("left", "one"), call("right", "two")), context=agent_runtime(host)
        )
        assert {item.tool_call_id: item.content for item in output["messages"][1:]} == {
            "left": "one",
            "right": "two",
        }
        for key in ("tool:left", "tool:right"):
            assert host.actions[key]["status"] == "succeeded"
            assert [event for event in host.events if event[1] == key] == [
                ("authorize", key),
                ("started", key),
                ("guard", key),
                ("guard", key),
                ("save", key),
            ]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "context",
    [None, {}, {"run_id": "run"}, {"host": object()}, {"host": object(), "run_id": "other"}],
)
def test_missing_or_mismatched_runtime_is_refused_before_platform_action(context):
    host = TraceHost()
    graph, _ = tool_graph([binding()])
    with pytest.raises(RuntimeFailure, match="tool_not_allowed"):
        asyncio.run(graph.ainvoke(message(call("one", "query")), context=context))
    assert not host.events


@pytest.mark.parametrize("mismatch", ["id", "tool", "registration"])
def test_inconsistent_call_or_binding_is_refused_before_action(mismatch):
    async def scenario():
        host = TraceHost()
        bound = binding()
        tools = prepare_agent_tools({"tools": [bound]}, [])
        tool = tools[0]
        tool_call = call("one", "query")
        runtime = tool_runtime(host, "wrong" if mismatch == "id" else "one")
        if mismatch == "tool":
            tool = StructuredTool.from_function(
                lambda query: query, name="wrong", description="wrong"
            )
        if mismatch == "registration":
            bound = {**bound, "exposed_name": "another"}
        middleware = ToolExecutionMiddleware({"tools": [bound]}, prepare_skills([], []), "run")
        request = ToolCallRequest(tool=tool, tool_call=tool_call, state={}, runtime=runtime)

        async def forbidden(_request):
            pytest.fail("Inconsistent calls must not reach a handler")

        with pytest.raises(RuntimeFailure, match="tool_not_allowed"):
            await middleware.awrap_tool_call(request, forbidden)
        assert not host.events and not host.received

    asyncio.run(scenario())


def test_authorization_precedes_execution_and_saved_feedback():
    async def scenario():
        host = TraceHost()
        graph, _ = tool_graph([binding()])
        output = await graph.ainvoke(message(call("one", "query")), context=agent_runtime(host))
        host.events.append(("feedback", output["messages"][-1].tool_call_id))
        assert host.events == [
            ("authorize", "tool:one"),
            ("started", "tool:one"),
            ("guard", "tool:one"),
            ("transport", "query"),
            ("guard", "tool:one"),
            ("preserve", "tool:one"),
            ("save", "tool:one"),
            ("feedback", "one"),
        ]
        host.denied = True
        with pytest.raises(RuntimeFailure, match="permission_denied"):
            await graph.ainvoke(message(call("two", "denied")), context=agent_runtime(host))
        assert host.events[-1] == ("authorize", "tool:two")
        assert len(host.received) == 1 and "tool:two" not in host.actions

    asyncio.run(scenario())


def test_result_save_failure_does_not_return_tool_feedback():
    async def scenario():
        host = TraceHost()
        host.fail_save = True
        graph, _ = tool_graph([binding()])
        with pytest.raises(RuntimeError, match="save failed"):
            await graph.ainvoke(message(call("one", "query")), context=agent_runtime(host))
        assert host.actions["tool:one"]["status"] == "running"
        assert host.events[-1] == ("save", "tool:one")

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["cancel", "error"])
def test_interrupted_mcp_call_does_not_leave_context_for_next_call(mode):
    async def scenario():
        host = TraceHost()
        entered = asyncio.Event()
        blocked = asyncio.Event()

        async def stop(_arguments):
            entered.set()
            if mode == "error":
                raise RuntimeError("upstream failed")
            await blocked.wait()

        host.before_return = stop
        graph, tools = tool_graph([binding()])
        task = asyncio.create_task(
            graph.ainvoke(message(call("old", "old")), context=agent_runtime(host))
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        if mode == "cancel":
            task.cancel()
        with pytest.raises(asyncio.CancelledError if mode == "cancel" else RuntimeError):
            await task
        assert host.actions["tool:old"]["status"] == ("running" if mode == "cancel" else "failed")
        assert not any(event == ("preserve", "tool:old") for event in host.events)
        host.before_return = None
        output = await graph.ainvoke(message(call("new", "new")), context=agent_runtime(host))
        assert json.loads(output["messages"][-1].content)["query"] == "new"
        assert host.actions["tool:new"]["status"] == "succeeded"
        assert tools[0].coroutine is None

    asyncio.run(scenario())


def test_cancelled_knowledge_call_joins_its_thread_before_returning():
    started, release, finished = Event(), Event(), Event()
    host = TraceHost()

    def knowledge(_name, arguments):
        started.set()
        assert release.wait(3)
        finished.set()
        return ToolOutcome(arguments["query"])

    host.knowledge_call = knowledge
    graph, _ = tool_graph([binding("knowledge")])

    async def scenario():
        task = asyncio.create_task(
            graph.ainvoke(message(call("old", "old")), context=agent_runtime(host))
        )
        try:
            assert await asyncio.to_thread(started.wait, 2)
            task.cancel()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.02)
            assert not finished.is_set() and not task.done()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert finished.is_set()
        assert host.actions["tool:old"]["status"] == "running"
        assert not any(event == ("save", "tool:old") for event in host.events)
        output = await graph.ainvoke(message(call("new", "new")), context=agent_runtime(host))
        assert output["messages"][-1].content == "new"
        assert host.actions["tool:new"]["status"] == "succeeded"

    asyncio.run(scenario())


def test_result_reader_uses_injected_host_and_hides_runtime_from_model_schema():
    async def scenario():
        host = TraceHost("trusted")
        host.load_tool_result = lambda _id: {"platform_result": {"binding_id": "binding:lookup"}}
        graph, tools = tool_graph([binding()])
        reader = next(tool for tool in tools if tool.name == "read_tool_result")
        assert "runtime" not in reader.tool_call_schema.model_json_schema()["properties"]
        output = await graph.ainvoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "read_tool_result",
                                "id": "read",
                                "args": {
                                    "result_id": "saved",
                                    "offset": 1,
                                    "limit": 20,
                                    "runtime": {"host": "forged", "run_id": "forged"},
                                },
                            }
                        ],
                    )
                ]
            },
            context=agent_runtime(host),
        )
        assert json.loads(output["messages"][-1].content) == {
            "host": "trusted",
            "result_id": "saved",
            "offset": 1,
            "limit": 20,
        }
        assert host.actions["tool:read"]["status"] == "succeeded"

    asyncio.run(scenario())


def test_checkpoint_resume_receives_new_host_without_persisting_runtime_context():
    async def scenario():
        before, after = TraceHost("before"), TraceHost("after")
        saver = InMemorySaver()
        graph, _ = tool_graph([binding()], saver=saver, interrupt_before=["tools"])
        config = {"configurable": {"thread_id": "thread"}}
        await graph.ainvoke(message(call("one", "query")), config, context=agent_runtime(before))
        assert not before.events
        saved = await graph.aget_state(config)
        assert set(saved.values) == {"messages"}
        output = await graph.ainvoke(None, config, context=agent_runtime(after))
        assert json.loads(output["messages"][-1].content)["host"] == "after"
        assert not before.events and after.actions["tool:one"]["status"] == "succeeded"
        assert "host" not in (await graph.aget_state(config)).values

    asyncio.run(scenario())


def durable_tool_graph(api_client, monkeypatch, *, failure=None):
    from langchain.tools import ToolRuntime
    from runtime_helpers import make_task
    from sqlalchemy import select
    from test_agent_foundations import workspace
    from test_capability_runtime import setup
    from test_conversations import send

    from app.execution.models import Run, RunAction

    _, _, agent, conversation = setup(api_client)
    workspace(api_client, agent, names=["read_file"], max_calls=1)
    run_id = send(api_client, conversation).json()["response"]["id"]
    store = api_client.app.state.run_worker.store
    assert store.claim(run_id)
    row, _ = store.load(run_id)
    bound = row.config_snapshot["tools"][0]
    events, sessions = [], []
    denied = [False]

    def authorize(active, db=None, invocation=None):
        events.append("authorize")
        sessions.append(db)
        if denied[0]:
            raise RuntimeFailure("permission_denied")
        return api_client.app.state.runs.authorize(row, active, db=db, invocation=invocation)

    control = make_task(run_id, store, authorize)
    start_action, finish_action = store._start_action, store.finish_action

    def start(db, *args, **kwargs):
        assert db is sessions[-1]
        events.append("start_action")
        if failure == "start":
            raise RuntimeError("start write failed")
        return start_action(db, *args, **kwargs)

    def finish(*args, **kwargs):
        events.append("finish_action")
        if failure == "finish":
            raise RuntimeError("result write failed")
        return finish_action(*args, **kwargs)

    monkeypatch.setattr(store, "_start_action", start)
    monkeypatch.setattr(store, "finish_action", finish)

    async def read_file(file_path: str, runtime: ToolRuntime[dict]) -> str:
        assert runtime.context["host"] is control
        assert runtime.context["run_id"] == run_id
        with store.database.transaction() as db:
            current = db.get(Run, run_id)
            action = db.scalar(select(RunAction).where(RunAction.run_id == run_id))
            assert current.tool_calls == 1 and action.status == "running"
        events.append("execute")
        return file_path

    tool = StructuredTool.from_function(coroutine=read_file, description="读取")
    graph, _ = tool_graph([bound], run_id, tools=[tool])
    value = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "id": "durable",
                        "args": {"file_path": "/workspace/data.txt"},
                    }
                ],
            )
        ]
    }
    return SimpleNamespace(
        graph=graph,
        value=value,
        context=agent_runtime(control, run_id),
        events=events,
        denied=denied,
        store=store,
        run_id=run_id,
    )


def test_real_action_transaction_authorizes_before_budget_and_reauthorizes_cached_result(
    api_client, monkeypatch
):
    from sqlalchemy import select

    from app.execution.models import Run, RunAction

    case = durable_tool_graph(api_client, monkeypatch)

    async def scenario():
        first = await case.graph.ainvoke(case.value, context=case.context)
        case.events.append("feedback")
        assert case.events == ["authorize", "start_action", "execute", "finish_action", "feedback"]
        cached = await case.graph.ainvoke(case.value, context=case.context)
        assert cached["messages"][-1].content == first["messages"][-1].content
        assert case.events[-1] == "authorize" and case.events.count("execute") == 1
        case.denied[0] = True
        with pytest.raises(RuntimeFailure, match="permission_denied"):
            await case.graph.ainvoke(case.value, context=case.context)
        assert case.events[-1] == "authorize" and case.events.count("execute") == 1

    asyncio.run(scenario())
    with case.store.database.transaction() as db:
        row = db.get(Run, case.run_id)
        actions = list(db.scalars(select(RunAction).where(RunAction.run_id == case.run_id)))
        assert row.tool_calls == 1 and len(actions) == 1
        assert actions[0].status == "succeeded" and actions[0].result_payload is not None


@pytest.mark.parametrize("failure", ["start", "finish"])
def test_database_failure_blocks_execution_or_feedback_at_the_correct_boundary(
    api_client, monkeypatch, failure
):
    from sqlalchemy import select

    from app.execution.models import Run, RunAction

    case = durable_tool_graph(api_client, monkeypatch, failure=failure)
    with pytest.raises(RuntimeError, match="write failed"):
        asyncio.run(case.graph.ainvoke(case.value, context=case.context))
    with case.store.database.transaction() as db:
        row = db.get(Run, case.run_id)
        action = db.scalar(select(RunAction).where(RunAction.run_id == case.run_id))
        if failure == "start":
            assert row.tool_calls == 0 and action is None
            assert "execute" not in case.events
        else:
            assert row.tool_calls == 1 and action.status == "running"
            assert action.result_payload is None and case.events[-1] == "finish_action"


def test_cancelling_one_run_does_not_cancel_another_run_using_the_same_tools():
    async def scenario():
        tools = prepare_agent_tools({"tools": [binding()]}, [])
        graphs = [tool_graph([binding()], str(i), tools=tools)[0] for i in range(2)]
        hosts = [TraceHost("cancelled"), TraceHost("continuing")]
        entered = [asyncio.Event(), asyncio.Event()]
        release = [asyncio.Event(), asyncio.Event()]

        def pause(index):
            async def wait(_arguments):
                entered[index].set()
                await release[index].wait()

            return wait

        for index, host in enumerate(hosts):
            host.before_return = pause(index)
        tasks = [
            asyncio.create_task(
                graph.ainvoke(
                    message(call("same", str(index))),
                    context=agent_runtime(hosts[index], str(index)),
                )
            )
            for index, graph in enumerate(graphs)
        ]
        try:
            await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered)), timeout=2)
            tasks[0].cancel()
            with pytest.raises(asyncio.CancelledError):
                await tasks[0]
            assert not tasks[1].done()
            release[1].set()
            output = await asyncio.wait_for(tasks[1], timeout=2)
            assert json.loads(output["messages"][-1].content)["host"] == "continuing"
            assert hosts[0].actions["tool:same"]["status"] == "running"
            assert hosts[1].actions["tool:same"]["status"] == "succeeded"
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(scenario())


def test_revocation_during_tool_call_blocks_result_preservation():
    async def scenario():
        host = TraceHost()

        async def revoke(_arguments):
            host.denied = True

        host.before_return = revoke
        graph, _ = tool_graph([binding()])
        with pytest.raises(RuntimeFailure, match="permission_denied"):
            await graph.ainvoke(message(call("one", "query")), context=agent_runtime(host))
        assert ("preserve", "tool:one") not in host.events
        assert host.actions["tool:one"]["status"] == "failed"
        assert host.events[-2:] == [("guard", "tool:one"), ("save", "tool:one")]

    asyncio.run(scenario())
