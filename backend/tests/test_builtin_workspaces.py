import os
import subprocess
import sys
import tomllib
from pathlib import Path

from dotenv import dotenv_values
from test_agent_foundations import send
from test_capability_runtime import ScriptedModel, execute, response, setup
from test_configuration_api import create_agent

ROOT = Path(__file__).resolve().parents[2]


def test_workspace_is_platform_capability_not_a_plugin(api_client):
    assert api_client.get("/api/tool-connections").json() == []
    assert api_client.get("/api/capabilities", params={"kind": "native"}).status_code == 422
    status = api_client.get("/api/tool-capabilities").json()
    assert status["workspace_mode"] == "virtual" and not status["execute_ready"]
    rejected = api_client.post(
        "/api/tool-connections",
        json={"name": "workspace", "kind": "native", "provider_key": "workspace"},
    )
    assert rejected.status_code == 422
    employee = create_agent(api_client)
    assert employee["tool_grants"] == []


def test_builtin_virtual_workspace_delivers_file_without_sandbox(api_client, monkeypatch):
    _, _, employee, conversation = setup(api_client)
    assert employee["tool_grants"] == []
    accepted = send(api_client, conversation)
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": "write_file",
                        "id": "output",
                        "args": {
                            "file_path": "/outputs/report.md",
                            "content": "# 工作结果\n已整理资料。",
                        },
                    }
                ],
            ),
            response("已生成文件。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    file = result["files"][0]
    downloaded = api_client.get(f"/api/conversations/{conversation['id']}/files/{file['id']}")
    assert downloaded.content.decode() == "# 工作结果\n已整理资料。"
    assert "execute" not in model.bindings[0]
    assert api_client.app.state.sandboxes.resources() == []


def initialize(tmp_path):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/init_sandbox.py"),
            "--directory",
            str(tmp_path / "sandbox"),
            "--app-env",
            str(tmp_path / ".env"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_sandbox_initialization_persists_shared_secret_without_enabling_execution(tmp_path):
    result = initialize(tmp_path)
    assert result.returncode == 0, result.stderr
    server = tmp_path / "sandbox/sandbox.toml"
    env = tmp_path / ".env"
    key = tomllib.loads(server.read_text())["server"]["api_key"]
    assert len(key) >= 40
    assert dotenv_values(env)["OPENSANDBOX_API_KEY"] == key
    assert key not in result.stdout + result.stderr
    assert not (tmp_path / "sandbox/verified-profile.json").exists()
    assert "OPENSANDBOX_IMAGE" not in dotenv_values(env)
    assert os.stat(server).st_mode & 0o777 == 0o600
    assert os.stat(env).st_mode & 0o777 == 0o600
    assert os.stat(server.parent).st_mode & 0o777 == 0o700
    before = (server.read_bytes(), env.read_bytes())
    assert initialize(tmp_path).returncode == 0
    assert before == (server.read_bytes(), env.read_bytes())


def test_sandbox_initialization_preserves_external_service_and_rejects_key_mismatch(tmp_path):
    env = tmp_path / ".env"
    external = "OPENSANDBOX_ENDPOINT=https://sandbox.example\nOPENSANDBOX_API_KEY=existing-secret\n"
    env.write_text(external)
    assert initialize(tmp_path).returncode == 1
    assert env.read_text() == external
    assert not (tmp_path / "sandbox/sandbox.toml").exists()
    env.write_text("OPENSANDBOX_API_KEY=existing-secret\nOTHER_SETTING=keep\n")
    assert initialize(tmp_path).returncode == 0
    server = tmp_path / "sandbox/sandbox.toml"
    assert tomllib.loads(server.read_text())["server"]["api_key"] == "existing-secret"
    original = server.read_bytes()
    env.write_text("OPENSANDBOX_API_KEY=different-secret\n")
    assert initialize(tmp_path).returncode == 1
    assert server.read_bytes() == original
