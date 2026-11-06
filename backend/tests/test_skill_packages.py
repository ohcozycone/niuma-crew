"""Portable Skill assets, frozen resources and the actual SDK loading boundary."""

import base64
import io
import stat
import zipfile
from types import SimpleNamespace

import pytest
from deepagents.backends.protocol import ExecuteResponse
from run_helpers import empty_conversation, read_reply
from test_capability_runtime import ScriptedModel, execute, response, submit

from app.errors import InvalidInputError
from app.execution.models import Run
from app.execution.runtime.skills import prepare_skills
from app.execution.runtime.workspace import WorkspaceBackend, _SandboxFileBackend
from app.skills.packages import archive_files, parse_skill_md

SOURCE = "---\nname: table-report\ndescription: Generate a report from an input table\nlicense: MIT\n---\nRead references/rules.md, then run scripts/analyze.py.\n"


def encoded_archive(files=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, body in (
            files
            or {
                "table-report/SKILL.md": SOURCE,
                "table-report/references/rules.md": "RULES_OLD：先核对行数。",
                "table-report/scripts/analyze.py": "print('report')\n",
                "table-report/assets/sample.bin": b"\x00\xff\x01",
            }
        ).items():
            archive.writestr(path, body)
    return base64.b64encode(stream.getvalue()).decode()


def imported(client):
    result = client.post(
        "/api/skills/import", json={"archive_base64": encoded_archive(), "name": "表格报告"}
    )
    assert result.status_code == 201, result.text
    return result.json()


def assigned(client, skill):
    connection = client.post(
        "/api/model-connections", json={"name": "测试大脑", "api_key": "fixture-secret"}
    ).json()
    agent = client.post(
        "/api/agents",
        json={
            "name": "表格员",
            "avatar_id": "admin",
            "model_connection_id": connection["id"],
            "skill_assignments": [{"skill_id": skill["id"]}],
        },
    ).json()
    return empty_conversation(client, agent["id"]), agent


def test_import_preview_is_inert_and_export_preserves_standard_source_and_binary(api_client):
    preview = api_client.post(
        "/api/skills/import/preview", json={"archive_base64": encoded_archive()}
    )
    assert preview.status_code == 200, preview.text
    assert len(preview.json()["files"]) == 4
    assert api_client.get("/api/skills").json()["total"] == 0
    assert not api_client.app.state.skills.blobs.directory.exists()
    skill = imported(api_client)
    assert skill["protocol_name"] == "table-report" and skill["name"] == "表格报告"
    assert skill["skill_md"] == SOURCE and len(skill["files"]) == 4
    resource = api_client.get(
        f"/api/skills/{skill['id']}/files", params={"path": "assets/sample.bin"}
    ).json()
    assert base64.b64decode(resource["content_base64"]) == b"\x00\xff\x01"
    exported = api_client.get(f"/api/skills/{skill['id']}/export")
    assert exported.status_code == 200 and exported.headers["content-type"] == "application/zip"
    files = archive_files(base64.b64encode(exported.content).decode())
    assert files["SKILL.md"].decode() == SOURCE
    assert files["assets/sample.bin"] == b"\x00\xff\x01"
    assert (
        api_client.get(
            f"/api/skills/{skill['id']}/files", params={"path": "../etc/passwd"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "files",
    [
        {"../SKILL.md": SOURCE},
        {"/SKILL.md": SOURCE},
        {"wrong-name/SKILL.md": SOURCE},
        {"a/SKILL.md": SOURCE, "b/SKILL.md": SOURCE},
        {"SKILL.md": SOURCE, "a/FILE.txt": "a", "a/file.txt": "b"},
        {"SKILL.md": SOURCE, "a": "a", "a/file.txt": "b"},
    ],
)
def test_archive_paths_duplicates_and_multiple_roots_are_rejected(files):
    with pytest.raises(InvalidInputError):
        archive_files(encoded_archive(files))


def test_zip_links_and_compression_bombs_are_rejected():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("SKILL.md", SOURCE)
        link = zipfile.ZipInfo("references/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "/etc/passwd")
    with pytest.raises(InvalidInputError):
        archive_files(base64.b64encode(stream.getvalue()).decode())
    with pytest.raises(InvalidInputError):
        archive_files(encoded_archive({"SKILL.md": SOURCE, "huge.txt": b"a" * 1000000}))


@pytest.mark.parametrize(
    "metadata",
    [
        "name: table-report\nname: another\ndescription: report",
        "name: table-report\ndescription: report\nmetadata: {value: .nan}",
        "name: table-report\ndescription: report\nextra: &loop [*loop]",
        "name: [table-report]\ndescription: report",
        "name: table-report\ndescription: {nested: report}",
    ],
)
def test_bad_yaml_is_a_classified_validation_failure(metadata):
    with pytest.raises(InvalidInputError):
        parse_skill_md("---\n" + metadata + "\n---\nInstructions")


def test_standard_unicode_lowercase_name_is_supported():
    assert (
        parse_skill_md("---\nname: café-report\ndescription: Report\n---\nRead")["name"]
        == "café-report"
    )


def test_skill_json_upload_above_normal_request_ceiling_is_supported(api_client):
    # Incompressible content deliberately exceeds the ordinary 1 MiB JSON limit.
    import random

    data = random.Random(42).randbytes(1024 * 1024)
    result = api_client.post(
        "/api/skills/import/preview",
        json={"archive_base64": encoded_archive({"SKILL.md": SOURCE, "assets/input.bin": data})},
    )
    assert result.status_code == 200, result.text
    assert result.json()["files"][1]["size"] == len(data)


def test_package_resource_edit_is_atomic_and_old_run_reads_frozen_bytes(api_client, monkeypatch):
    skill = imported(api_client)
    conversation, _ = assigned(api_client, skill)
    run = submit(api_client, conversation, [skill["id"]]).json()["response"]
    with api_client.app.state.database.transaction() as db:
        snapshot = db.get(Run, run["id"]).config_snapshot
        old_manifest = snapshot["skills"][0]["package_manifest"]
    files = []
    for descriptor in skill["files"]:
        content = api_client.get(
            f"/api/skills/{skill['id']}/files", params={"path": descriptor["path"]}
        ).json()
        files.append(
            {
                key: value
                for key, value in content.items()
                if key in {"path", "content", "content_base64"}
            }
        )
    next(item for item in files if item["path"] == "references/rules.md")["content"] = "RULES_NEW"
    updated = api_client.patch(
        f"/api/skills/{skill['id']}", json={"expected_revision": 1, "package_files": files}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["id"] == skill["id"] and updated.json()["revision"] == 2
    assert (
        api_client.patch(
            f"/api/skills/{skill['id']}", json={"expected_revision": 1, "package_files": files}
        ).status_code
        == 409
    )
    assert (
        api_client.get(
            f"/api/skills/{skill['id']}/files", params={"path": "references/rules.md"}
        ).json()["content"]
        == "RULES_NEW"
    )
    old = next(item for item in old_manifest if item["path"] == "references/rules.md")
    assert b"RULES_OLD" in api_client.app.state.skills.read_blob(old["content_hash"])
    path = f"/skills/s-{skill['id']}/references/rules.md"
    model = ScriptedModel(
        responses=[
            response("", [{"name": "read_file", "id": "resource", "args": {"file_path": path}}]),
            response("报告"),
        ]
    )
    assert execute(api_client, monkeypatch, model, run)["status"] == "succeeded"
    assert "RULES_OLD" in model.prompts[-1] and "RULES_NEW" not in model.prompts[-1]
    # A supporting file read is not falsely recorded as another full activation.
    actions = read_reply(api_client, run["id"])["steps"]
    assert sum(item["kind"] == "skill_activation" for item in actions) == 1


def test_legacy_inputs_outputs_and_examples_are_present_when_pinned(api_client, monkeypatch):
    skill = api_client.post(
        "/api/skills",
        json={
            "name": "旧技能",
            "instructions": "STEPS",
            "input_description": "INPUT_MARKER",
            "output_description": "OUTPUT_MARKER",
            "example": "EXAMPLE_MARKER",
        },
    ).json()
    conversation, _ = assigned(api_client, skill)
    run = submit(api_client, conversation, [skill["id"]]).json()["response"]
    model = ScriptedModel(responses=[response("已按方法处理")])
    assert execute(api_client, monkeypatch, model, run)["status"] == "succeeded"
    assert all(
        marker in model.prompts[0]
        for marker in ("STEPS", "INPUT_MARKER", "OUTPUT_MARKER", "EXAMPLE_MARKER")
    )


def test_standard_description_has_one_source_and_legacy_patch_still_works(api_client):
    skill = imported(api_client)
    rejected = api_client.patch(
        f"/api/skills/{skill['id']}",
        json={"expected_revision": 1, "description": "A divergent description"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "skill_source_required"
    current = api_client.get(f"/api/skills/{skill['id']}").json()
    assert current["revision"] == 1 and current["skill_md"] == SOURCE
    source = SOURCE.replace(
        "Generate a report from an input table", "Review a table before reporting"
    )
    updated = api_client.patch(
        f"/api/skills/{skill['id']}",
        json={"expected_revision": 1, "skill_md": source, "description": "ignored legacy field"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Review a table before reporting"
    assert updated.json()["skill_md"] == source
    legacy = api_client.post("/api/skills", json={"name": "旧方法", "instructions": "正文"}).json()
    result = api_client.patch(
        f"/api/skills/{legacy['id']}",
        json={"expected_revision": 1, "description": "旧入口仍可编辑"},
    )
    assert result.status_code == 200 and result.json()["description"] == "旧入口仍可编辑"


def test_resources_cannot_be_read_from_unassigned_package(api_client, monkeypatch):
    skill = imported(api_client)
    conversation, agent = assigned(api_client, skill)
    other = api_client.post(
        "/api/skills", json={"name": "另一方法", "instructions": "只读方法"}
    ).json()
    updated = api_client.patch(
        f"/api/agents/{agent['id']}",
        json={"expected_revision": 1, "skill_assignments": [{"skill_id": other["id"]}]},
    )
    assert updated.status_code == 200, updated.text
    run = submit(api_client, conversation).json()["response"]
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": "read_file",
                        "id": "resource",
                        "args": {"file_path": f"/skills/s-{skill['id']}/references/rules.md"},
                    }
                ],
            )
        ]
    )
    result = execute(api_client, monkeypatch, model, run)
    assert result["status"] == "failed" and result["error"]["code"] == "skill_not_allowed"


def test_skill_tool_declarations_never_install_or_grant_execution(api_client, monkeypatch):
    source = SOURCE.replace("license: MIT", "license: MIT\nallowed-tools: execute")
    skill = api_client.post("/api/skills", json={"name": "声明执行", "skill_md": source}).json()
    conversation, _ = assigned(api_client, skill)
    run = submit(api_client, conversation, [skill["id"]]).json()["response"]
    model = ScriptedModel(responses=[response("仅依照方法回答")])
    assert execute(api_client, monkeypatch, model, run)["status"] == "succeeded"
    assert all(binding == ["read_file"] for binding in model.bindings)


def test_storage_failure_never_publishes_partial_skill(api_client, monkeypatch):
    store = api_client.app.state.skills.blobs
    original = store.put
    calls = 0

    def failing(data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("fixture-disk-error")
        return original(data)

    monkeypatch.setattr(store, "put", failing)
    response = api_client.post("/api/skills/import", json={"archive_base64": encoded_archive()})
    assert calls == 2
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "internal_error"
    assert response.headers["X-Request-ID"]
    assert "fixture-disk-error" not in response.text
    assert api_client.get("/api/skills").json()["total"] == 0


def test_skill_bytes_materialize_only_for_active_skill_and_remain_readonly():
    digest = "a" * 64
    item = {
        "skill_id": "test-id",
        "name": "表格",
        "description": "规则",
        "instructions": "Run scripts/analyze.py",
        "parameters": {},
        "package_manifest": [
            {"path": "scripts/analyze.py", "content_hash": digest, "is_text": True}
        ],
    }
    prepared = prepare_skills([item], [])
    written, commands, executions = [], [], []
    fake = SimpleNamespace(
        id="fake",
        commands=SimpleNamespace(
            run=lambda command, *, opts: (
                commands.append((command, opts)) or SimpleNamespace(exit_code=0)
            )
        ),
        files=SimpleNamespace(write_files=lambda entries: written.extend(entries)),
    )
    backend = _SandboxFileBackend(sandbox=fake, timeout=60)
    backend.execute = lambda command, *, timeout: (
        executions.append(command) or ExecuteResponse(output="ok", exit_code=0)
    )
    resources = SimpleNamespace(
        tools=None,
        read_file=lambda _: b"",
        list_sources=lambda: [],
        save_source=lambda *args: {},
        save_output=lambda *args: {},
        sandbox=SimpleNamespace(acquire=lambda: fake),
        read_skill_blob=lambda key: b"print('frozen')" if key == digest else b"",
    )
    workspace = WorkspaceBackend(
        {"workspace": {"mode": "sandbox"}}, prepared, resources, sandbox_factory=lambda _: backend
    )
    # Merely loading descriptions does not create a sandbox.
    assert workspace.remote is None
    workspace.execute("echo plain")
    assert written == []
    prepared.active_skill_ids.add("test-id")
    workspace.execute("python /skills/s-test-id/scripts/analyze.py")
    assert {entry.path for entry in written} == {
        "/skills/s-test-id/SKILL.md",
        "/skills/s-test-id/scripts/analyze.py",
    }
    assert all(entry.mode == 0o444 and entry.owner == "root" for entry in written)
    assert commands[0][1].uid == commands[0][1].gid == 0
    assert executions[-1] == "python /skills/s-test-id/scripts/analyze.py"
    workspace.execute("echo again")
    assert len(written) == 2
