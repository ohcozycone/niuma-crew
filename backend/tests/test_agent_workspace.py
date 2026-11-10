from types import SimpleNamespace

import pytest
from deepagents.backends import StateBackend
from deepagents.backends.protocol import ExecuteResponse
from deepagents.middleware.filesystem import FilesystemMiddleware
from test_agent_foundations import FakeProvider, send
from test_capability_runtime import ScriptedModel, execute, response, setup

from app.common.errors import ConflictError, PermissionDeniedError
from app.resources.environments.service import RunSandbox
from app.runtime.agent.skills import prepare_skills
from app.runtime.execution.models import Run
from app.runtime.tools.workspace import WorkspaceBackend


def test_default_workspace_matches_official_tools_and_schemas_without_grants(api_client):
    _, _, employee, conversation = setup(api_client)
    accepted = send(api_client, conversation)
    row, _ = api_client.app.state.run_worker.store.load(accepted["id"])
    bindings = {
        item["tool_name"]: item
        for item in row.config_snapshot["tools"]
        if item["kind"] == "workspace"
    }
    official = {
        tool.name: tool
        for tool in FilesystemMiddleware(backend=StateBackend()).tools
        if tool.name != "execute"
    }
    assert not employee["tool_grants"] and bindings.keys() == official.keys()
    for name, tool in official.items():
        assert bindings[name]["description"] == tool.description
        assert bindings[name]["input_schema"] == tool.get_input_schema().model_json_schema()
    assert row.config_snapshot["checkpoint_resumable"]


def test_tool_disabled_work_has_no_file_or_execution_capabilities(api_client, monkeypatch):
    _, _, employee, _ = setup(api_client)
    monkeypatch.setattr("app.resources.environments.service.load_verification", lambda _: {})
    with api_client.app.state.database.transaction() as db:
        snapshot, _ = api_client.app.state.runs.configuration.prepare(
            db, employee["id"], "仅回答问题", [], tools_enabled=False
        )
    assert snapshot["tools"] == [] and snapshot["skills"] == []
    assert snapshot["workspace"] == {"mode": "virtual", "read_roots": [], "write_roots": []}


def test_ready_sandbox_is_lazy_for_plain_chat(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    provider = FakeProvider()
    api_client.app.state.sandboxes.provider = provider
    monkeypatch.setattr("app.resources.environments.service.load_verification", lambda _: {})
    accepted = send(api_client, conversation)
    model = ScriptedModel(responses=[response("直接回答即可。")])
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert "execute" in model.bindings[0]
    assert provider.created == 0 and api_client.app.state.sandboxes.resources() == []


def test_frozen_sandbox_configuration_cannot_change_before_start(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    monkeypatch.setattr("app.resources.environments.service.load_verification", lambda _: {})
    accepted = send(api_client, conversation)
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, accepted["id"])
        row.config_snapshot = {
            **row.config_snapshot,
            "workspace": {**row.config_snapshot["workspace"], "image": "different-image"},
        }
    model = ScriptedModel(responses=[response("不应调用")])
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "sandbox_configuration_changed"
    assert not model.bindings


def test_first_virtual_write_disables_replay_and_keeps_delivered_file(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    accepted = send(api_client, conversation)
    store = api_client.app.state.run_worker.store
    assert store.load(accepted["id"])[0].config_snapshot["checkpoint_resumable"]
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": "write_file",
                        "id": "write",
                        "args": {"file_path": "/outputs/report.md", "content": "已核对的结果"},
                    }
                ],
            ),
            response("已生成文件。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    row, _ = store.load(accepted["id"])
    assert row.config_snapshot["checkpoint_resumable"] is False
    assert api_client.app.state.files.read(result["files"][0]["id"]) == "已核对的结果".encode()


@pytest.mark.parametrize(
    "path", ["/inputs/a.txt", "/sources/a.txt", "/skills/a.txt", "/etc/passwd"]
)
def test_base_workspace_never_writes_readonly_or_host_paths(path):
    backend = WorkspaceBackend(
        {
            "workspace": {
                "mode": "virtual",
                "read_roots": ["/inputs", "/sources", "/skills"],
                "write_roots": ["/workspace", "/outputs"],
            }
        },
        prepare_skills([], []),
        SimpleNamespace(),
    )
    with pytest.raises(PermissionDeniedError):
        backend.write(path, "cannot write")


def test_file_operations_and_execute_share_one_remote_and_raw_source_bytes():
    files, events = {}, []

    class Remote:
        def check_path(self, path, *, write=False):
            events.append(("check", path))

        def write(self, path, content):
            files[path] = content.encode()

        def materialize_readonly(self, values):
            files.update(values)

        def execute(self, command, *, timeout):
            assert files["/workspace/script.py"] == b"print('computed')"
            assert files["/sources/source/data.bin"] == b"\xff\x00\r\n"
            events.append(("execute", timeout))
            return ExecuteResponse(output="computed", exit_code=0)

    def acquire():
        events.append(("acquire", None))
        return object()

    backend = WorkspaceBackend(
        {
            "workspace": {
                "mode": "sandbox",
                "read_roots": ["/workspace", "/sources"],
                "write_roots": ["/workspace"],
                "command_seconds": 30,
            }
        },
        prepare_skills([], []),
        SimpleNamespace(
            sandbox=SimpleNamespace(acquire=acquire),
            list_sources=lambda: [{"id": "source", "name": "data.bin"}],
            read_file=lambda _: b"\xff\x00\r\n",
        ),
        sandbox_factory=lambda _: Remote(),
    )
    backend.write("/workspace/script.py", "print('computed')")
    assert backend.execute("python3 /workspace/script.py", timeout=500).output == "computed"
    backend.execute("python3 /workspace/script.py")
    assert events.count(("acquire", None)) == 1
    assert events.count(("execute", 30)) == 2


def test_released_run_sandbox_cannot_create_another_environment(api_client, monkeypatch):
    monkeypatch.setattr("app.resources.environments.service.load_verification", lambda _: {})
    sandbox = api_client.app.state.sandboxes.for_run("100000000000", [], lambda _: b"")
    sandbox.release()
    with pytest.raises(ConflictError) as caught:
        sandbox.acquire()
    assert caught.value.code == "runtime_interrupted"


def test_cleanup_failure_still_closes_local_client_and_preserves_original_error():
    closed = []

    def release(_):
        raise RuntimeError("resource persistence failed")

    sandbox = RunSandbox(SimpleNamespace(release=release), "run", [], lambda _: b"")
    sandbox.handle = SimpleNamespace(close=lambda: closed.append(True))
    with pytest.raises(RuntimeError, match="resource persistence failed"):
        sandbox.release()
    assert sandbox.handle is None and sandbox.closed and closed == [True]
