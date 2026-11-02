"""Foundation acceptance: actual SDK loop and SQLite, with bounded fake upstreams."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from test_capability_runtime import ScriptedModel, execute, response, setup

from app.agent_runtime.sandbox_backend import SandboxFileBackend
from app.agents.models import AgentToolGrant
from app.errors import ConflictError, InvalidInputError
from app.execution.control import RunControl
from app.execution.models import Run, RunAction
from app.files.models import StoredFile
from app.sandboxes.models import SandboxResource
from app.sandboxes.service import SandboxService
from app.tools.adapters.mcp import MCPClient
from app.tools.config import ToolConfig
from app.tools.contracts import ToolInvocation, digest, exposed_name
from app.tools.network import BoundedStream, PinnedTransport


def workspace(client, agent, *, mode="virtual", names=None, max_calls=32):
    created = client.post(
        "/api/tool-connections",
        json={
            "name": "工作区" + str(uuid4()),
            "kind": "native",
            "provider_key": "workspace",
            "public_config": {"workspace_mode": mode},
        },
    )
    assert created.status_code == 201, created.text
    connection = created.json()
    grant = client.put(
        f"/api/agents/{agent['id']}/tool-grants",
        json={
            "expected_revision": agent["revision"],
            "grants": [
                {
                    "connection_id": connection["id"],
                    "tools": names or ["read_file", "write_file", "ls"],
                    "scope_policy": {
                        "mode": "workspace",
                        "max_calls": max_calls,
                        "read_roots": ["/inputs", "/sources", "/workspace", "/outputs"],
                        "write_roots": ["/workspace", "/outputs"],
                    },
                }
            ],
        },
    )
    assert grant.status_code == 200, grant.text
    return connection, grant.json()


def send(client, conversation, *, files=None):
    accepted = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={
            "content": "处理输入并交付文件",
            "file_ids": files or [],
            "client_request_id": str(uuid4()),
        },
    )
    assert accepted.status_code == 202, accepted.text
    return accepted.json()


def run_id(client, accepted):
    if "response" not in accepted:
        return accepted["id"]
    with client.app.state.database.transaction() as db:
        from app.conversations.models import ConversationRun

        return db.scalar(
            select(ConversationRun.run_id).where(
                ConversationRun.reply_message_id == accepted["response"]["id"]
            )
        )


def test_file_sdk_upload_publish_and_download_survive_working_state(api_client, monkeypatch):
    _, _, agent, conversation = setup(api_client)
    workspace(api_client, agent)
    uploaded = api_client.post(
        "/api/files?name=data.csv", content=b"a,b\n1,2\n", headers={"content-type": "text/csv"}
    )
    assert uploaded.status_code == 201, uploaded.text
    ref = uploaded.json()
    accepted = send(api_client, conversation, files=[ref["id"]])
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": "read_file",
                        "id": "input",
                        "args": {"file_path": f"/inputs/{ref['id']}/data.csv"},
                    }
                ],
            ),
            response(
                "",
                [
                    {
                        "name": "write_file",
                        "id": "output",
                        "args": {"file_path": "/outputs/result.csv", "content": "sum\n3\n"},
                    }
                ],
            ),
            response("已生成结果。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, {"id": run_id(api_client, accepted)})
    assert result["status"] == "succeeded", result
    output = result["files"][0]
    downloaded = api_client.get(f"/api/conversations/{conversation['id']}/files/{output['id']}")
    assert (
        downloaded.content == b"sum\n3\n"
        and downloaded.headers["x-content-type-options"] == "nosniff"
    )
    assert all(step["kind"] != "skill_activation" for step in result["steps"])
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, run_id(api_client, accepted))
        assert row.tool_calls == 2 and row.skill_reads == 0
        assert not row.config_snapshot["checkpoint_resumable"]
        assert all(
            action.result_payload and action.result_ref
            for action in db.scalars(
                select(RunAction).where(RunAction.run_id == row.id, RunAction.kind == "tool_call")
            )
        )
    other = api_client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    assert (
        api_client.get(f"/api/conversations/{other['id']}/files/{output['id']}").status_code == 404
    )
    history = api_client.get(f"/api/conversations/{conversation['id']}/messages").json()
    assert history["items"][0]["files"][0]["id"] == ref["id"]
    assert history["items"][-1]["files"][0]["id"] == output["id"]


def test_file_denial_and_atomic_budget_failure_do_not_execute(api_client, monkeypatch):
    _, _, agent, conversation = setup(api_client)
    workspace(api_client, agent, names=["read_file"], max_calls=1)
    accepted = send(api_client, conversation)
    id = run_id(api_client, accepted)
    store = api_client.app.state.execution_store
    store.claim(id)
    row, _ = store.load(id)
    binding = row.config_snapshot["tools"][0]

    def auth(active, db=None, invocation=None):
        return api_client.app.state.runner.coordinator.authorize(
            row, active, db=db, invocation=invocation
        )

    control = RunControl(id, store, auth)
    denied = ToolInvocation(
        "tool:denied", binding["binding_id"], "read_file", {"file_path": "/inputs/../app.db"}
    )
    with pytest.raises(Exception, match="文件路径"):
        asyncio.run(control.begin_tool(denied))
    invocation = ToolInvocation(
        "tool:first", binding["binding_id"], "read_file", {"file_path": "/workspace/a.txt"}
    )
    original = store._start_action
    monkeypatch.setattr(
        store,
        "_start_action",
        lambda *a, **kw: (_ for _ in ()).throw(OperationalError("injected", {}, Exception())),
    )
    with pytest.raises(OperationalError):
        asyncio.run(control.begin_tool(invocation))
    with api_client.app.state.database.transaction() as db:
        assert db.get(Run, id).tool_calls == 0
    monkeypatch.setattr(store, "_start_action", original)
    asyncio.run(control.begin_tool(invocation))
    with pytest.raises(Exception) as caught:
        asyncio.run(
            control.begin_tool(
                ToolInvocation(
                    "tool:second",
                    binding["binding_id"],
                    "read_file",
                    {"file_path": "/workspace/b.txt"},
                )
            )
        )
    assert caught.value.code == "agent_budget_exceeded"


def test_mcp_official_adapter_discovers_and_calls_real_protocol():
    from fastmcp import FastMCP

    server = FastMCP("foundation-protocol")

    @server.tool
    async def search(query: str) -> dict:
        return {"results": [{"url": "https://example.com", "content": query}]}

    app = server.http_app(path="/mcp", stateless_http=True)
    client = MCPClient(
        "https://fixture.test/mcp",
        {},
        ToolConfig(),
        transport_factory=lambda: httpx.ASGITransport(app=app),
    )

    async def scenario():
        async with app.router.lifespan_context(app):
            catalog = await client.discover()
            assert catalog[0]["name"] == "search"
            guards = []

            async def guard():
                guards.append(True)

            content, artifact, status = await client.invoke(
                "search", {"query": "official"}, catalog[0]["descriptor_hash"], guard
            )
            assert status == "success" and "official" in json.dumps([content, artifact])
            assert guards == [True]
            with pytest.raises(InvalidInputError) as caught:
                await client.invoke("search", {"query": "x"}, "changed", guard)
            assert caught.value.code == "tool_catalog_changed"

    asyncio.run(scenario())


class SearchClient:
    calls = 0
    before_guard = None
    catalog = [
        {
            "name": "tavily_search",
            "description": "Search current official sources",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "descriptor_hash": digest("search-v1"),
            "recovery": "never",
        }
    ]

    def __init__(self, *args):
        pass

    async def discover(self):
        return self.catalog

    async def invoke(self, name, arguments, expected_hash, guard):
        if self.before_guard:
            self.before_guard()
        await guard()
        type(self).calls += 1
        return (
            [],
            {
                "structured_content": {
                    "results": [
                        {
                            "url": "https://example.com/docs",
                            "title": "说明",
                            "content": "正文" * 20000,
                        }
                    ]
                }
            },
            "success",
        )


def search_grant(client, agent):
    client.app.state.tool_invocation.client_factory = SearchClient
    connection = client.post(
        "/api/tool-connections",
        json={
            "name": "搜索",
            "kind": "mcp_http",
            "auth_type": "bearer",
            "credential": "fixture-tool-secret",
            "public_config": {"url": "https://mcp.tavily.com/mcp"},
        },
    ).json()
    candidate = client.post(f"/api/tool-connections/{connection['id']}/discover").json()
    approved = client.post(
        f"/api/tool-connections/{connection['id']}/approve",
        json={
            "expected_config_revision": candidate["config_revision"],
            "expected_catalog_revision": candidate["catalog_revision"],
            "candidate_hash": candidate["discovery_candidate"]["hash"],
        },
    )
    assert approved.status_code == 200, approved.text
    saved = client.put(
        f"/api/agents/{agent['id']}/tool-grants",
        json={
            "expected_revision": agent["revision"],
            "grants": [
                {
                    "connection_id": connection["id"],
                    "tools": ["tavily_search"],
                    "expected_descriptors": {
                        "tavily_search": approved.json()["approved_catalog"][0]["descriptor_hash"]
                    },
                    "scope_policy": {"mode": "provider", "max_calls": 5},
                }
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    assert "fixture-tool-secret" not in json.dumps(connection)
    return connection


def test_search_model_call_records_sources_and_long_result(api_client, monkeypatch):
    _, _, agent, conversation = setup(api_client)
    SearchClient.calls, SearchClient.before_guard = 0, None
    connection = search_grant(api_client, agent)
    accepted = send(api_client, conversation)
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": exposed_name(connection["id"], "tavily_search"),
                        "id": "search",
                        "args": {"query": "当前说明"},
                    }
                ],
            ),
            response("找到说明，尚未读取全文。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, {"id": run_id(api_client, accepted)})
    assert result["status"] == "succeeded", result
    assert SearchClient.calls == 1
    step = next(step for step in result["steps"] if step["kind"] == "tool_call")
    source = step["safe_details"]["sources"][0]
    assert not source["full_text"] and source["url"] == "https://example.com/docs"
    assert (
        api_client.get(
            f"/api/conversations/{conversation['id']}/files/{source['file_id']}"
        ).content.decode()
        == "正文" * 20000
    )
    assert max(len(prompt.encode()) for prompt in model.prompts) < 131072


def test_current_tools_reach_http_model_with_old_unavailable_history(api_client, monkeypatch):
    from app.llm.factory import create_chat_model

    _, _, agent, conversation = setup(api_client)
    previous = send(api_client, conversation)
    result = execute(
        api_client,
        monkeypatch,
        ScriptedModel(responses=[response("当前会话没有联网读取网页的工具。")]),
        {"id": run_id(api_client, previous)},
    )
    assert result["status"] == "succeeded"
    connection = search_grant(api_client, agent)
    name = exposed_name(connection["id"], "tavily_search")
    SearchClient.calls = 0
    requests = []

    def upstream(request):
        body = json.loads(request.content)
        requests.append(body)
        first = len(requests) == 1
        delta = (
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "search-current-tools",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps({"query": "文档"})},
                    }
                ],
            }
            if first
            else {"role": "assistant", "content": "已取得实际搜索结果。"}
        )
        chunks = [
            {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {
                "choices": [
                    {"index": 0, "delta": {}, "finish_reason": "tool_calls" if first else "stop"}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        ]
        content = "".join(
            "data: "
            + json.dumps({"id": "fixture", "object": "chat.completion.chunk", **chunk})
            + "\n\n"
            for chunk in chunks
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=content + "data: [DONE]\n\n",
        )

    @asynccontextmanager
    async def model_session(config, *, max_tokens):
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as transport:
            yield create_chat_model(config, transport=transport, max_tokens=max_tokens)

    monkeypatch.setattr("app.agent_runtime.langchain.model_session", model_session)
    accepted = send(api_client, conversation)
    id = run_id(api_client, accepted)
    asyncio.run(api_client.app.state.runner.coordinator.run(id))
    completed = api_client.get(f"/api/runs/{id}").json()
    for request in requests:
        tools = {tool["function"]["name"]: tool["function"] for tool in request["tools"]}
        assert name in tools and "query" in tools[name]["parameters"]["properties"]
        system = json.dumps(request["messages"][0]["content"], ensure_ascii=False)
        assert "本轮工具状态" in system and name in system and "tavily_search" in system
        assert any(
            message["role"] == "assistant" and "没有联网" in str(message["content"])
            for message in request["messages"]
        ), request["messages"]
    assert completed["status"] == "succeeded", completed
    assert len(requests) == 2 and SearchClient.calls == 1
    assert any(step["kind"] == "tool_call" for step in completed["steps"])


def test_revocation_during_mcp_preflight_blocks_actual_request(api_client, monkeypatch):
    _, _, agent, conversation = setup(api_client)
    SearchClient.calls = 0
    connection = search_grant(api_client, agent)

    def revoke():
        with api_client.app.state.database.transaction() as db:
            grant = db.scalar(select(AgentToolGrant).where(AgentToolGrant.agent_id == agent["id"]))
            grant.enabled = False

    SearchClient.before_guard = staticmethod(revoke)
    try:
        accepted = send(api_client, conversation)
        result = execute(
            api_client,
            monkeypatch,
            ScriptedModel(
                responses=[
                    response(
                        "",
                        [
                            {
                                "name": exposed_name(connection["id"], "tavily_search"),
                                "id": "revoke",
                                "args": {"query": "x"},
                            }
                        ],
                    )
                ]
            ),
            {"id": run_id(api_client, accepted)},
        )
        assert result["status"] == "failed" and SearchClient.calls == 0
        assert result["error"]["code"] == "tool_access_revoked"
    finally:
        SearchClient.before_guard = None


def test_bounded_receive_and_explicit_private_network_policy(monkeypatch):
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"1234"
            yield b"5678"

    async def read():
        async for _ in BoundedStream(Stream(), 6):
            pass

    with pytest.raises(InvalidInputError) as caught:
        asyncio.run(read())
    assert caught.value.code == "tool_result_too_large"
    with pytest.raises(InvalidInputError):
        PinnedTransport("http://127.0.0.1:123/mcp", ToolConfig())


class FakeProvider:
    def __init__(self):
        self.ids, self.created, self.killed = [], 0, []
        self.fail_create, self.fail_kill = False, False

    def create(self, metadata):
        self.created += 1
        self.metadata = metadata
        if self.fail_create:
            raise TimeoutError()
        self.ids = ["owned-sandbox"]
        return SimpleNamespace(id=self.ids[0], close=lambda: None)

    def initialize(self, *args):
        pass

    def find(self, metadata):
        assert metadata == self.metadata
        return self.ids

    def kill(self, id):
        if self.fail_kill:
            raise TimeoutError()
        self.killed.append(id)
        self.ids = []


def test_sandbox_create_unknown_keeps_debt_and_late_resource_is_collected(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    accepted = send(api_client, conversation)
    id = run_id(api_client, accepted)
    provider = FakeProvider()
    provider.fail_create = True
    service = SandboxService(
        api_client.app.state.database,
        api_client.app.state.sandboxes.config,
        lambda: [],
        provider=provider,
    )
    monkeypatch.setattr("app.sandboxes.service.load_verification", lambda _: {})
    with pytest.raises(TimeoutError):
        service.acquire(id, [], lambda _: b"")
    with api_client.app.state.database.transaction() as db:
        row = db.scalar(select(SandboxResource).where(SandboxResource.run_id == id))
        assert row.state == "unknown"
    with pytest.raises(ConflictError):
        service.acquire(id, [], lambda _: b"")
    assert provider.created == 1
    provider.ids = ["late-owned-sandbox"]
    service.sweep()
    assert provider.killed == ["late-owned-sandbox"]
    with api_client.app.state.database.transaction() as db:
        assert db.get(SandboxResource, row.id).state == "destroyed"


def test_sandbox_sdk_commands_are_unprivileged_and_bounded():
    calls = []

    def run(command, *, opts, handlers):
        calls.append(opts)
        handlers.on_stdout(SimpleNamespace(text="done"))
        return SimpleNamespace(exit_code=0)

    backend = SandboxFileBackend(
        sandbox=SimpleNamespace(id="fake", commands=SimpleNamespace(run=run)), timeout=60
    )
    assert backend.execute("python script.py", timeout=500).output == "done"
    assert calls[0].uid == calls[0].gid == 1000
    assert calls[0].timeout == timedelta(seconds=60)

    def flood(command, *, opts, handlers):
        handlers.on_stdout(SimpleNamespace(text="x" * 65537))

    backend._sandbox.commands.run = flood
    with pytest.raises(InvalidInputError):
        backend.execute("flood")


def test_legacy_v2_recovery_is_not_invalidated(api_client):
    _, _, _, conversation = setup(api_client)
    accepted = send(api_client, conversation)
    id = run_id(api_client, accepted)
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, id)
        row.config_snapshot = {
            **row.config_snapshot,
            "schema_version": 2,
            "checkpoint_resumable": True,
        }
    assert api_client.app.state.execution_store.recover(resume=True) == []


def test_default_https_port_dns_pin_and_tls_name_are_preserved(monkeypatch):
    async def scenario():
        async def resolve(*args, **kwargs):
            return [(2, 1, 6, "", ("1.1.1.1", 443))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        seen = []

        def upstream(request):
            seen.append(request)
            assert request.url.host == "1.1.1.1"
            assert request.headers["host"] == "mcp.tavily.com"
            assert request.extensions["sni_hostname"] == "mcp.tavily.com"
            return httpx.Response(401, content=b"unauthorized")

        transport = PinnedTransport("https://mcp.tavily.com/mcp", ToolConfig())
        transport.inner = httpx.MockTransport(upstream)
        async with httpx.AsyncClient(transport=transport) as client:
            assert (await client.get("https://mcp.tavily.com/mcp")).status_code == 401
        assert len(seen) == 1

    asyncio.run(scenario())


def test_reference_retention_keeps_published_outputs_and_cleans_orphans(api_client, monkeypatch):
    from app.conversations.files import retained_file_ids
    from app.infrastructure.database.fields import utc_now

    _, _, agent, conversation = setup(api_client)
    workspace(api_client, agent)
    accepted = send(api_client, conversation)
    result = execute(
        api_client,
        monkeypatch,
        ScriptedModel(
            responses=[
                response(
                    "",
                    [
                        {
                            "name": "write_file",
                            "id": "out",
                            "args": {"file_path": "/outputs/a.txt", "content": "retained"},
                        }
                    ],
                ),
                response("完成"),
            ]
        ),
        {"id": run_id(api_client, accepted)},
    )
    assert result["status"] == "succeeded"
    with api_client.app.state.database.transaction() as db:
        owner = db.get(Run, run_id(api_client, accepted)).owner_user_id
    orphan = api_client.app.state.files.save(owner, "unused.txt", b"orphan")
    with api_client.app.state.database.transaction() as db:
        for row in db.scalars(select(StoredFile)):
            row.created_at = utc_now() - timedelta(days=2)
    api_client.app.state.files.sweep(retained_file_ids)
    assert api_client.app.state.files.read(result["files"][0]["id"]) == b"retained"
    with api_client.app.state.database.transaction() as db:
        assert db.get(StoredFile, orphan["id"]) is None


def test_agent_execute_uses_owned_sandbox_collects_then_destroys(api_client, monkeypatch):
    _, _, agent, conversation = setup(api_client)
    workspace(api_client, agent, mode="sandbox", names=["execute"])
    events = []

    class Provider(FakeProvider):
        def create(self, metadata):
            handle = super().create(metadata)
            events.append("create")

            def run(command, *, opts, handlers=None):
                assert opts.uid in (0, 1000)
                if command.startswith("pkill"):
                    events.append("stop")
                    return SimpleNamespace(exit_code=0)
                assert opts.uid == opts.gid == 1000
                text = '["/outputs/result.csv"]' if "os.walk" in command else "2"
                if "os.walk" not in command:
                    events.append("execute")
                handlers.on_stdout(SimpleNamespace(text=text))
                return SimpleNamespace(exit_code=0)

            def read(path):
                events.append("download")
                assert path == "/outputs/result.csv"
                return b"value\n2\n"

            handle.commands = SimpleNamespace(run=run)
            handle.files = SimpleNamespace(read_bytes=read)
            return handle

        def kill(self, id):
            events.append("kill")
            super().kill(id)

    provider = Provider()
    api_client.app.state.sandboxes.provider = provider
    monkeypatch.setattr("app.sandboxes.service.load_verification", lambda _: {})
    accepted = send(api_client, conversation)
    id = run_id(api_client, accepted)
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": "execute",
                        "id": "compute",
                        "args": {"command": "python3 -c 'print(1+1)'"},
                    }
                ],
            ),
            response("计算完成，文件已生成。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, {"id": id})
    assert result["status"] == "succeeded", result
    assert (
        events.index("execute")
        < events.index("stop")
        < events.index("download")
        < events.index("kill")
    )
    output = result["files"][0]
    assert (
        api_client.get(f"/api/conversations/{conversation['id']}/files/{output['id']}").content
        == b"value\n2\n"
    )
    with api_client.app.state.database.transaction() as db:
        resource = db.scalar(select(SandboxResource).where(SandboxResource.run_id == id))
        assert resource.state == "destroyed"


def test_parallel_tools_cannot_spend_the_same_last_budget(api_client):
    from concurrent.futures import ThreadPoolExecutor

    _, _, agent, conversation = setup(api_client)
    workspace(api_client, agent, names=["read_file"], max_calls=1)
    id = run_id(api_client, send(api_client, conversation))
    store = api_client.app.state.execution_store
    store.claim(id)
    row, _ = store.load(id)
    binding = row.config_snapshot["tools"][0]

    def auth(active, db=None, invocation=None):
        return api_client.app.state.runner.coordinator.authorize(
            row, active, db=db, invocation=invocation
        )

    control = RunControl(id, store, auth)

    def reserve(number):
        try:
            asyncio.run(
                control.begin_tool(
                    ToolInvocation(
                        f"tool:{number}",
                        binding["binding_id"],
                        "read_file",
                        {"file_path": "/workspace/a.txt"},
                    )
                )
            )
            return "accepted"
        except Exception as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == ["accepted", "agent_budget_exceeded"]
    with api_client.app.state.database.transaction() as db:
        assert db.get(Run, id).tool_calls == 1


def test_long_source_line_has_bounded_read_windows_without_changing_original():
    from deepagents.backends.utils import file_data_to_string

    from app.agent_runtime.skill_loading import prepare_skills
    from app.agent_runtime.workspace import WorkspaceBackend

    raw = "资料" * 10000
    reads = []

    def read_file(id):
        reads.append(id)
        return raw.encode()

    resources = SimpleNamespace(
        list_sources=lambda: [{"id": "source", "name": "page.txt"}], read_file=read_file
    )
    snapshot = {
        "tools": [
            {"kind": "native", "scope_policy": {"read_roots": ["/sources"], "write_roots": []}}
        ]
    }
    backend = WorkspaceBackend(snapshot, prepare_skills([], []), resources)
    offset, pieces = 0, []
    while True:
        result = backend.read("/sources/source/page.txt", offset, 2000)
        text = file_data_to_string(result.file_data) if result.file_data else ""
        if not text:
            break
        assert len(text.encode()) < 16000
        pieces.append(text.replace("\n", ""))
        if result.next_offset is None:
            break
        offset = result.next_offset
    assert "".join(pieces) == raw and reads == ["source"]
