import asyncio
import json

import pytest
from langchain_core.messages import ToolMessage
from sqlalchemy import select
from test_agent_foundations import SearchClient
from test_capability_runtime import ScriptedModel, discovery_response, execute, response, submit
from test_tool_readers import search_setup

from app.resources.employees.models import AgentToolGrant
from app.resources.mcp.contracts import exposed_name
from app.runtime.agent.model_calls import model_input_bytes
from app.runtime.execution.context import RunContext
from app.runtime.execution.models import RunAction
from app.runtime.tools.result_files import ToolResultBackend
from app.runtime.tools.results import feedback_outcome


def provider(monkeypatch, text):
    async def invoke(self, name, arguments, expected_hash, guard):
        await guard()
        return (
            [{"type": "text", "text": text}],
            {"structured_content": {"opaque": "keep"}},
            "success",
        )

    monkeypatch.setattr(SearchClient, "invoke", invoke)


def search_model(connection, *after):
    return ScriptedModel(
        responses=[
            discovery_response(),
            response(
                "",
                [
                    {
                        "name": exposed_name(connection["id"], "catalog_search"),
                        "id": "search",
                        "args": {"query": "test"},
                    }
                ],
            ),
            *after,
        ]
    )


def test_summary_after_repeated_long_line_reads_keeps_current_task(api_client, monkeypatch):
    from configuration_helpers import set_submission_limits

    _, conversation, connection = search_setup(api_client)
    set_submission_limits(
        api_client.app.state.conversation_commands,
        summary_trigger_tokens=8000,
        summary_keep_tokens=2000,
    )
    raw = json.dumps({"rows": ["x" * 24000], "tail": "TAIL_MARKER"})
    provider(monkeypatch, raw)
    question = "CURRENT_TASK：统计 Notion 文章数量；证据不足时说明未知。"
    accepted = submit(api_client, conversation, content=question).json()["response"]
    reads = [
        response(
            "",
            [
                {
                    "name": "read_file",
                    "id": identifier,
                    "args": {
                        "file_path": "/sources/large_tool_results/search",
                        "offset": 0,
                        "limit": 1,
                    },
                }
            ],
        )
        for identifier in ("read-first", "read-again")
    ]
    model = search_model(
        connection,
        *reads,
        response("任务：统计 Notion 文章数量，结果只读到前缀，总量未知。"),
        response("目前不能确认文章总数。"),
    )
    done = execute(api_client, monkeypatch, model, accepted)
    assert done["status"] == "succeeded", done
    assert "Previous conversation was too long to summarize" not in model.prompts[-1]
    assert len(model.prompts) == 6
    assert question in model.prompts[-2]
    assert "统计 Notion 文章数量" in model.prompts[-1]
    with api_client.app.state.database.transaction() as db:
        actions = list(db.scalars(select(RunAction).where(RunAction.run_id == accepted["id"])))
        summaries = [a for a in actions if a.safe_details.get("purpose") == "summary"]
        assert len(summaries) == 1 and summaries[0].status == "succeeded"


@pytest.mark.parametrize("offset,expected_status", [(0, "succeeded"), (999999, "failed")])
def test_character_read_request_and_budget_closing_complete_run(
    api_client, monkeypatch, offset, expected_status
):
    from configuration_helpers import set_submission_limits

    _, conversation, connection = search_setup(api_client)
    set_submission_limits(api_client.app.state.conversation_commands, max_model_calls=4)
    provider(
        monkeypatch, json.dumps({"body": "正文" * 12000, "tail": "TAIL_MARKER"}, ensure_ascii=False)
    )
    accepted = submit(api_client, conversation).json()["response"]

    class Reader(ScriptedModel):
        def _generate(self, messages, *args, **kwargs):
            if self._index == 2:
                text = next(m.content for m in reversed(messages) if isinstance(m, ToolMessage))
                hint = next(
                    json.loads(line) for line in text.splitlines() if line.startswith('{"tool":')
                )
                self.responses[2] = response(
                    "",
                    [
                        {
                            "name": "read_tool_result",
                            "id": "read",
                            "args": {
                                **hint["arguments"],
                                "offset": offset,
                                "limit": 15000,
                            },
                        }
                    ],
                )
            elif self._index == 3:
                latest = next(m for m in reversed(messages) if isinstance(m, ToolMessage))
                if expected_status == "succeeded":
                    page = json.loads(latest.content)
                    assert len(page["text"].encode()) <= 8000 and page["next_offset"] > 0
                else:
                    assert latest.status == "error" and "参数" in latest.content
            return super()._generate(messages, *args, **kwargs)

    model = Reader(
        responses=search_model(
            connection, response("placeholder"), response("已有证据不足，总数未知。")
        ).responses
    )
    done = execute(api_client, monkeypatch, model, accepted)
    assert done["status"] == "succeeded", done
    assert len(model.prompts) == 4 and "本次运行只剩最后一次模型调用" in model.prompts[-1]
    with api_client.app.state.database.transaction() as db:
        actions = list(db.scalars(select(RunAction).where(RunAction.run_id == accepted["id"])))
        read = next(a for a in actions if a.call_key == "tool:read")
        assert read.status == expected_status
        final = next(a for a in actions if a.action_key == "model:4")
        assert (
            final.safe_details["final_response_only"]
            and final.safe_details["exposed_tool_ids"] == []
        )


def test_last_budget_request_reaches_chat_api_without_tools(api_client, monkeypatch):
    import httpx
    from test_capability_runtime import setup

    from app.infrastructure.llm.config import LLMConfig
    from app.infrastructure.llm.factory import create_chat_model
    from app.runtime.execution.models import Run

    _, _, _, conversation = setup(api_client)
    accepted = submit(api_client, conversation, content="统计文章数量").json()["response"]
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        final = len(requests) == 8
        if final:
            assert "tools" not in body and "tool_choice" not in body
            assert "本次运行只剩最后一次模型调用" in str(body["messages"])
            message = {"role": "assistant", "content": "已有证据不足，文章总数未知。"}
        else:
            assert len(requests) < 8 and body["tools"]
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"read-{len(requests)}",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"file_path": "/workspace/missing.txt"}),
                        },
                    }
                ],
            }
        delta = dict(message)
        if not final:
            delta["tool_calls"] = [{"index": 0, **message["tool_calls"][0]}]
        finish = "stop" if final else "tool_calls"
        base = {"id": "fixture", "model": "fixture", "created": 1}
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        if body.get("stream"):
            events = [
                {
                    **base,
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "delta": delta,
                            "finish_reason": finish,
                        }
                    ],
                },
                {**base, "object": "chat.completion.chunk", "choices": [], "usage": usage},
            ]
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                text="".join("data: " + json.dumps(event) + "\n\n" for event in events)
                + "data: [DONE]\n\n",
            )
        return httpx.Response(
            200,
            json={
                **base,
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": finish,
                    }
                ],
                "usage": usage,
            },
        )

    transport = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        model = create_chat_model(
            LLMConfig(api_key="fixture", model_id="fixture", base_url="https://fixture.invalid/v1"),
            transport=transport,
        )
        done = execute(api_client, monkeypatch, model, accepted)
    finally:
        asyncio.run(transport.aclose())
    assert done["status"] == "succeeded", done
    assert len(requests) == 8
    with api_client.app.state.database.transaction() as db:
        assert db.get(Run, accepted["id"]).model_calls == 8


def test_long_single_line_feedback_exposes_working_character_reader(api_client, monkeypatch):
    _, conversation, connection = search_setup(api_client)
    raw = '{"rows":["' + "正文" * 12000 + '"],"tail":"TAIL_MARKER"}'
    provider(monkeypatch, raw)
    accepted = submit(api_client, conversation).json()["response"]

    class Reader(ScriptedModel):
        result_id: str = ""

        def _generate(self, messages, *args, **kwargs):
            if self._index in (2, 3):
                text = next(m.content for m in reversed(messages) if isinstance(m, ToolMessage))
                hint = next(
                    json.loads(line) for line in text.splitlines() if line.startswith('{"tool":')
                )
                assert hint["tool"] == "read_tool_result"
                assert hint["arguments"]["offset"] == 0
                if self._index == 2:
                    self.result_id = hint["arguments"]["result_id"]
                else:
                    assert hint["arguments"]["result_id"] == self.result_id
                    assert "truncated mid-line" in text and "TAIL_MARKER" not in text
                    self.responses[3] = response(
                        "",
                        [
                            {
                                "name": hint["tool"],
                                "id": "read-tail",
                                "args": {"result_id": self.result_id, "offset": len(raw) - 100},
                            }
                        ],
                    )
            elif self._index == 4:
                page = json.loads(
                    next(m.content for m in reversed(messages) if isinstance(m, ToolMessage))
                )
                assert page["text"] == raw[-100:] and page["next_offset"] is None
            return super()._generate(messages, *args, **kwargs)

    model = Reader(
        responses=search_model(
            connection,
            response(
                "",
                [
                    {
                        "name": "read_file",
                        "id": "read-line",
                        "args": {
                            "file_path": "/sources/large_tool_results/search",
                            "offset": 0,
                            "limit": 1,
                        },
                    }
                ],
            ),
            response("placeholder"),
            response("已读到末尾标记；不能据此确认文章总数。"),
        ).responses
    )
    done = execute(api_client, monkeypatch, model, accepted)
    assert done["status"] == "succeeded", done
    assert len(model.prompts) == 5
    with api_client.app.state.database.transaction() as db:
        source = db.scalar(
            select(RunAction).where(
                RunAction.run_id == accepted["id"], RunAction.call_key == "tool:search"
            )
        )
        assert source.result_payload["data"]["file_id"] == model.result_id
    body = api_client.get(f"/api/conversations/{conversation['id']}/files/{model.result_id}").json()
    assert body["text"] == raw


def test_oversized_summary_stops_before_request_without_replacing_task():
    from langchain_core.messages import AIMessage, HumanMessage
    from runtime_helpers import MemoryContext

    from app.runtime.agent.errors import RuntimeFailure
    from app.runtime.agent.model_calls import RunUsage, create_summarization_middleware

    messages = [HumanMessage(content="CURRENT_TASK")]
    for index, text in enumerate(["data" * 3000, "recent"]):
        messages.extend(
            [
                AIMessage(
                    content="", tool_calls=[{"id": str(index), "name": "read_file", "args": {}}]
                ),
                ToolMessage(content=text, tool_call_id=str(index)),
            ]
        )
    model = ScriptedModel(responses=[response("不应请求")])
    context = MemoryContext()
    middleware = create_summarization_middleware(
        model,
        {
            "context_bytes": 1024,
            "summary_trigger_tokens": 200,
            "summary_keep_tokens": 40,
        },
        context,
        RunUsage({}),
    )
    with pytest.raises(RuntimeFailure, match="context_limit_exceeded"):
        asyncio.run(middleware.abefore_model({"messages": messages}, None))
    assert not model.prompts and context.model_calls == 0
    assert messages[0].content == "CURRENT_TASK" and len(messages) == 5


@pytest.mark.parametrize(
    "kind,reader_present", [("workspace", True), ("knowledge", True), ("mcp_http", False)]
)
def test_character_read_hint_does_not_advertise_unavailable_capability(kind, reader_present):
    from app.runtime.contracts.tools import ToolInvocation
    from app.runtime.tools.result_files import ResultScope, result_read_hint
    from app.runtime.tools.results import result_reader_binding

    binding = {"kind": kind, "binding_id": "origin", "exposed_name": "source"}
    scope = ResultScope(
        ToolInvocation("tool:call", "origin", "source", {}),
        aliases={
            "/call": {"origin_binding_id": "origin", "content_ref": "file"},
        },
    )
    assert (
        result_read_hint(scope, [binding, *([result_reader_binding()] if reader_present else [])])
        == ""
    )


def test_small_complete_json_is_not_cut_or_wrapped(api_client, monkeypatch):
    _, conversation, connection = search_setup(api_client)
    raw = json.dumps(
        {"rows": [{"id": i, "body": "正文" * 30} for i in range(150)], "complete": True},
        ensure_ascii=False,
    )
    assert len(raw.encode()) > 24576
    provider(monkeypatch, raw)
    accepted = submit(api_client, conversation).json()["response"]
    model = search_model(connection, response("完成"))
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert raw in model.prompts[-1]
    with api_client.app.state.database.transaction() as db:
        action = db.scalar(
            select(RunAction).where(
                RunAction.run_id == accepted["id"], RunAction.call_key == "tool:search"
            )
        )
        assert json.loads(action.result_payload["content"]) == json.loads(raw)
        assert "result_aliases" not in action.result_payload["data"]["artifact"]


def test_native_alias_recreated_from_durable_action_and_rechecks_permission(
    api_client, monkeypatch
):
    _, conversation, connection = search_setup(api_client)
    raw = "\n".join(f"ROW-{i:04d} " + "正文" * 100 for i in range(300))
    provider(monkeypatch, raw)
    accepted = submit(api_client, conversation).json()["response"]
    model = search_model(
        connection,
        response(
            "",
            [
                {
                    "name": "read_file",
                    "id": "read",
                    "args": {
                        "file_path": "/sources/large_tool_results/search",
                        "offset": 150,
                        "limit": 1,
                    },
                }
            ],
        ),
        response("读取中间段完成"),
    )
    contexts = []
    original = RunContext.complete_tool

    async def capture(self, permit, outcome):
        contexts.append(self)
        return await original(self, permit, outcome)

    monkeypatch.setattr(RunContext, "complete_tool", capture)
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert "ROW-0150" in model.prompts[-1]
    backend = ToolResultBackend(contexts[-1])
    assert backend.download_files(["/search"])[0].content.decode() == raw
    downloaded = backend.download_files(["/missing", "/search"])
    assert len(downloaded) == 2 and downloaded[0].error == "file_not_found"
    assert downloaded[1].content.decode() == raw
    refs = api_client.app.state.files.sources(accepted["id"])
    assert len(refs) == 1
    with api_client.app.state.database.transaction() as db:
        action = db.scalar(
            select(RunAction).where(
                RunAction.run_id == accepted["id"], RunAction.call_key == "tool:search"
            )
        )
        assert "/sources/large_tool_results/search" in action.result_payload["content"]
        assert (
            action.result_payload["data"]["artifact"]["result_aliases"]["/search"]["content_ref"]
            == refs[0]["id"]
        )
        read = db.scalar(
            select(RunAction).where(
                RunAction.run_id == accepted["id"], RunAction.call_key == "tool:read"
            )
        )
        assert read.result_payload["data"]["artifact"]["source_reads"][0]["source_ranges"] is None
        db.scalar(select(AgentToolGrant)).enabled = False
    for operation in [
        lambda: backend.read("/search"),
        lambda: backend.grep("ROW", "/"),
        lambda: backend.download_files(["/search"]),
    ]:
        with pytest.raises(Exception, match="许可"):
            operation()
    assert asyncio.run(backend.awrite("/new", "forged")).error == "file_readonly"


def test_raw_save_failure_never_delivers_result(api_client, monkeypatch):
    _, conversation, connection = search_setup(api_client)
    provider(monkeypatch, "business result")
    accepted = submit(api_client, conversation).json()["response"]
    files = api_client.app.state.files
    original = files.save

    def fail(*args, **kwargs):
        if kwargs.get("purpose") == "source":
            raise OSError("synthetic failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(files, "save", fail)
    model = search_model(connection, response("不应调用"))
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "failed"
    assert len(model.prompts) == 2


def test_sdk_offload_failure_is_checked_before_model(api_client, monkeypatch):
    from deepagents.backends.protocol import WriteResult

    _, conversation, connection = search_setup(api_client)
    provider(monkeypatch, "正文" * 40000)
    accepted = submit(api_client, conversation).json()["response"]
    from app.runtime.execution.models import Run

    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, accepted["id"])
        row.config_snapshot = {**row.config_snapshot, "summary_trigger_tokens": 1000000}

    async def fail(*args, **kwargs):
        return WriteResult(error="synthetic write failure")

    monkeypatch.setattr(ToolResultBackend, "awrite", fail)
    model = search_model(connection, response("不应调用"))
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "failed" and result["error"]["code"] == "context_limit_exceeded"
    assert len(model.prompts) == 2
    assert len(api_client.app.state.files.sources(accepted["id"])) == 1


def test_feedback_preserves_json_and_multimodal_while_artifact_is_not_model_input():
    raw = json.dumps({"text": "正文" * 10000}, ensure_ascii=False)
    message = ToolMessage(content=raw, tool_call_id="test", artifact={"opaque": "x" * 150000})
    outcome = feedback_outcome(message)
    assert outcome.content == raw and json.loads(message.content)["text"] == "正文" * 10000
    assert model_input_bytes([message]) == model_input_bytes(
        [message.model_copy(update={"artifact": None})]
    )
    assert model_input_bytes([message]) < 100000
    blocks = [
        {"type": "text", "text": "caption"},
        {"type": "image_url", "image_url": {"url": "https://fixture.invalid/image.png"}},
    ]
    image = ToolMessage(content=blocks, tool_call_id="image")
    assert feedback_outcome(image).data["model_content"] == blocks
    assert image.content == blocks


def test_parallel_large_results_keep_separate_origins_and_single_archives(api_client, monkeypatch):
    _, conversation, connection = search_setup(api_client)

    async def invoke(self, name, arguments, expected_hash, guard):
        await guard()
        text = arguments["query"] + "\n" + ("data " * 5000)
        return [{"type": "text", "text": text}], {}, "success"

    monkeypatch.setattr(SearchClient, "invoke", invoke)
    accepted = submit(api_client, conversation).json()["response"]
    name = exposed_name(connection["id"], "catalog_search")
    model = ScriptedModel(
        responses=[
            discovery_response(),
            response(
                "",
                [
                    {"name": name, "id": identifier, "args": {"query": identifier}}
                    for identifier in ["first", "second"]
                ],
            ),
            response(
                "",
                [
                    {
                        "name": "read_file",
                        "id": "read",
                        "args": {"file_path": "/sources/large_tool_results/second", "limit": 1},
                    }
                ],
            ),
            response("已读取第二份结果"),
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert "1\tsecond" in model.prompts[-1] or "second" in model.prompts[-1]
    refs = api_client.app.state.files.sources(accepted["id"])
    assert len(refs) == 2
    with api_client.app.state.database.transaction() as db:
        actions = list(
            db.scalars(
                select(RunAction).where(
                    RunAction.run_id == accepted["id"],
                    RunAction.call_key.in_(["tool:first", "tool:second"]),
                )
            )
        )
        identities = [
            a.result_payload["data"]["artifact"]["result_aliases"][
                "/" + a.call_key.removeprefix("tool:")
            ]["content_ref"]
            for a in actions
        ]
        assert len(set(identities)) == 2
        read = db.scalar(
            select(RunAction).where(
                RunAction.run_id == accepted["id"], RunAction.call_key == "tool:read"
            )
        )
        second = next(a for a in actions if a.call_key == "tool:second")
        assert (
            read.result_payload["data"]["artifact"]["source_reads"][0]["content_ref"]
            == second.result_payload["data"]["file_id"]
        )


def test_cancel_during_offload_does_not_dispatch_next_model(api_client, monkeypatch):
    _, conversation, connection = search_setup(api_client)
    provider(monkeypatch, "data " * 5000)
    accepted = submit(api_client, conversation).json()["response"]
    original = ToolResultBackend.awrite

    async def cancelled(self, path, content):
        result = await original(self, path, content)
        with api_client.app.state.database.transaction() as db:
            from app.runtime.execution.models import Run

            api_client.app.state.runs.cancel(db, db.get(Run, accepted["id"]))
        return result

    monkeypatch.setattr(ToolResultBackend, "awrite", cancelled)
    model = search_model(connection, response("不应发布"))
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "cancelled", result
    assert len(model.prompts) == 2


def test_image_only_mcp_result_does_not_serialize_image_into_text():
    from runtime_helpers import agent_runtime
    from test_tool_runtime import TraceHost, binding, call, message, tool_graph

    from app.runtime.contracts.tools import ToolOutcome

    class Images(TraceHost):
        async def mcp_call(self, bound, arguments, guard):
            await super().mcp_call(bound, arguments, guard)
            return ToolOutcome(
                "",
                data={
                    "host": self.name,
                    **arguments,
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "https://fixture.invalid/image.png"},
                        }
                    ],
                },
            )

    async def scenario():
        host = Images()
        graph, _ = tool_graph([binding()], host=host)
        state = await graph.ainvoke(message(call("image", "fixture")), context=agent_runtime(host))
        result = state["messages"][-1]
        assert len(result.content) == 1 and result.content[0]["type"] == "image_url"
        assert result.text == ""

    asyncio.run(scenario())


def test_failed_result_status_is_visible_beyond_application_metadata():
    from types import SimpleNamespace

    from app.runtime.contracts.tools import ToolInvocation
    from app.runtime.execution.tool_results import ToolResults

    bodies = []

    def save(name, body):
        bodies.append(body)
        return {"id": "source", "name": name}

    results = ToolResults(
        {"tools": [{"binding_id": "source", "kind": "mcp_http"}]}, SimpleNamespace(save_source=save)
    )
    raw = {"content": [{"type": "text", "text": "partial rows"}]}
    text, _, _ = asyncio.run(
        results.preserve(ToolInvocation("tool:call", "source", "read", {}), raw, "failed")
    )
    assert json.loads(text) == {"status": "failed", "returned_content": "partial rows"}
    assert json.loads(bodies[0])["data"] == raw
    assert json.loads(bodies[0])["text"] == text


def test_sandbox_materializes_native_result_path_as_frozen_text():
    from types import SimpleNamespace

    from app.common.values import digest
    from app.runtime.agent.skills import prepare_skills
    from app.runtime.tools.workspace import WorkspaceBackend

    text = '{"rows":[1,2,3]}'
    entry = {"content_ref": "raw", "origin_binding_id": "origin", "content_hash": digest(text)}
    context = SimpleNamespace(
        tool_result_aliases=lambda: {"/source": entry},
        load_tool_result=lambda identifier: {
            "platform_result": {"binding_id": "origin"},
            "text": text,
        },
        list_sources=lambda: [],
        sandbox=SimpleNamespace(acquire=lambda: "handle"),
    )
    files = ToolResultBackend(context)
    saved = []
    work = SimpleNamespace(
        materialize_readonly=lambda pairs: saved.extend(pairs),
        execute=lambda *args, **kwargs: "done",
    )
    workspace = WorkspaceBackend(
        {"workspace": {"mode": "sandbox"}},
        prepare_skills([], []),
        context,
        sandbox_factory=lambda handle: work,
        result_sources=files.sources,
    )
    assert workspace.execute("read source") == "done"
    assert saved == [("/sources/large_tool_results/source", text.encode())]
    workspace.execute("read again")
    assert len(saved) == 1


@pytest.mark.parametrize("kind", ["source", "workspace"])
def test_followup_missing_file_is_feedback_and_does_not_abort_run(api_client, monkeypatch, kind):
    _, conversation, connection = search_setup(api_client)
    provider(monkeypatch, "ARCHIVED_CONTENT " * 2000)
    path = "/sources/large_tool_results/search" if kind == "source" else "/workspace/draft.txt"
    first = submit(api_client, conversation).json()["response"]
    create = (
        search_model(connection, response("资料已保存"))
        if kind == "source"
        else ScriptedModel(
            responses=[
                response(
                    "",
                    [
                        {
                            "name": "write_file",
                            "id": "save",
                            "args": {"file_path": path, "content": "DRAFT_CONTENT"},
                        }
                    ],
                ),
                response("草稿已保存"),
            ]
        )
    )
    assert execute(api_client, monkeypatch, create, first)["status"] == "succeeded"
    second = submit(api_client, conversation, content="继续读取刚才的资料").json()["response"]
    model = ScriptedModel(
        responses=[
            response("", [{"name": "read_file", "id": "reread", "args": {"file_path": path}}]),
            response("旧临时资料当前不可读取，需要重新取得。"),
        ]
    )
    done = execute(api_client, monkeypatch, model, second)
    assert done["status"] == "succeeded", done
    assert "not found" in model.prompts[-1].lower()
    assert len(model.prompts) == 2
