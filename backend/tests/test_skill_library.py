"""Portable directory writes, publication and preservation of employee identity."""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import select
from test_skill_packages import SOURCE, assigned, encoded_archive, imported

from app.skills.config import SkillConfig
from app.skills.models import Skill
from app.skills.service import SkillService


def sync(client):
    response = client.post("/api/skills/sync", json={})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("custom_directory", [False, True])
def test_user_library_default_and_explicit_root_discover_installed_packages(
    api_client, tmp_path, monkeypatch, custom_directory
):
    home = tmp_path / "user"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    root = tmp_path / "volume" if custom_directory else home / ".agents" / "skills"
    skill_dir = root / "table-report"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SOURCE)
    service = SkillService(
        api_client.app.state.skills.database,
        SkillConfig(library_directory=root if custom_directory else None),
    )
    assert service.library.root == root
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    result = service.sync_library(actor)
    assert result["items"][0]["status"] == "added"
    skill = service.get(result["items"][0]["skill_id"], actor)
    assert skill.name == "table-report" and skill.assignment_count == 0
    if custom_directory:
        assert not (home / ".agents" / "skills").exists()


def test_upload_and_directory_sync_share_files_and_preserve_alias_and_assignment(api_client):
    skill = imported(api_client)
    _, agent = assigned(api_client, skill)
    library = api_client.app.state.skills.library
    root = library.root / "table-report"
    assert (root / "SKILL.md").read_text() == SOURCE
    assert (root / "assets/sample.bin").read_bytes() == b"\x00\xff\x01"
    first = sync(api_client)
    assert first["items"][0]["status"] == "unchanged"
    assert first["items"][0]["skill_id"] == skill["id"]
    (root / "references/rules.md").write_text("NEW RULES")
    second = sync(api_client)
    assert second["items"][0]["status"] == "updated"
    current = api_client.get(f"/api/skills/{skill['id']}").json()
    assert current["name"] == "表格报告"
    assert current["assignment_count"] == 1
    assert current["revision"] == skill["revision"] + 1
    assert (
        api_client.get(f"/api/agents/{agent['id']}").json()["skill_assignments"][0]["skill_id"]
        == skill["id"]
    )
    old = next(item for item in skill["files"] if item["path"] == "references/rules.md")
    assert api_client.app.state.skills.read_blob(old["content_hash"]) != b"NEW RULES"
    assert sync(api_client)["items"][0]["status"] == "unchanged"


def test_command_line_install_is_discovered_without_execution(api_client):
    root = api_client.app.state.skills.library.root / "table-report"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(SOURCE)
    (root / "scripts").mkdir()
    (root / "scripts/must-not-run.py").write_text("raise RuntimeError('must not run')")
    result = sync(api_client)
    assert result["items"][0]["status"] == "added"
    skill = api_client.get(f"/api/skills/{result['items'][0]['skill_id']}").json()
    assert skill["name"] == "table-report" and skill["assignment_count"] == 0
    assert len(skill["files"]) == 2


def test_external_edits_block_platform_overwrite_until_synced(api_client):
    skill = imported(api_client)
    root = api_client.app.state.skills.library.root / "table-report"
    external = SOURCE + "\nExternal edit\n"
    (root / "SKILL.md").write_text(external)
    response = api_client.patch(
        f"/api/skills/{skill['id']}",
        json={"expected_revision": skill["revision"], "skill_md": SOURCE + "\nPlatform edit\n"},
    )
    assert response.status_code == 409
    assert (root / "SKILL.md").read_text() == external
    sync(api_client)
    current = api_client.get(f"/api/skills/{skill['id']}").json()
    response = api_client.patch(
        f"/api/skills/{skill['id']}",
        json={"expected_revision": current["revision"], "skill_md": external + "\nSaved\n"},
    )
    assert response.status_code == 200, response.text
    assert (root / "SKILL.md").read_text().endswith("Saved\n")


def test_missing_source_preserves_published_skill_and_can_be_restored(api_client):
    skill = imported(api_client)
    root = api_client.app.state.skills.library.root / "table-report"
    shutil.rmtree(root)
    assert sync(api_client)["items"][0]["status"] == "missing"
    assert api_client.get(f"/api/skills/{skill['id']}").json()["source_missing"]
    assert api_client.get(f"/api/skills/{skill['id']}/export").status_code == 200
    duplicate = api_client.post(
        "/api/skills/import",
        json={"archive_base64": encoded_archive()},
    )
    assert duplicate.status_code == 409
    assert not root.exists()  # DB rejection restores the filesystem as well.


def test_directory_conflicts_and_links_do_not_replace_published_content(api_client, tmp_path):
    skill = imported(api_client)
    root = api_client.app.state.skills.library.root
    (root / "invalid").mkdir()
    (root / "invalid/SKILL.md").write_text(SOURCE)
    (root / "escape").symlink_to(tmp_path)
    result = sync(api_client)
    assert {item["status"] for item in result["items"]} == {"unchanged", "error"}
    assert api_client.get(f"/api/skills/{skill['id']}").json()["revision"] == skill["revision"]


def test_database_rejection_restores_directory(api_client):
    skill = imported(api_client)
    assigned(api_client, skill)
    root = api_client.app.state.skills.library.root / "table-report"
    original = (root / "SKILL.md").read_bytes()
    # Invalid employee parameter schema is checked after the staged replacement.
    response = api_client.patch(
        f"/api/skills/{skill['id']}",
        json={
            "expected_revision": skill["revision"],
            "skill_md": SOURCE + "\nChanged",
            "configuration_schema": {
                "type": "object",
                "required": ["missing"],
                "properties": {"missing": {"type": "string"}},
            },
        },
    )
    assert response.status_code == 422, response.text
    assert (root / "SKILL.md").read_bytes() == original
    assert api_client.delete(f"/api/skills/{skill['id']}").status_code == 409
    assert root.exists()


def test_legacy_directory_materialization_does_not_duplicate_or_increment_revision(api_client):
    skill = imported(api_client)
    service = api_client.app.state.skills
    shutil.rmtree(service.library.root / "table-report")
    with service.database.transaction() as db:
        db.scalar(select(Skill).where(Skill.id == skill["id"])).source_path = None
    result = sync(api_client)
    assert result["items"][0]["status"] == "unchanged"
    assert result["items"][0]["skill_id"] == skill["id"]
    assert api_client.get("/api/skills").json()["total"] == 1
    assert api_client.get(f"/api/skills/{skill['id']}").json()["revision"] == skill["revision"]


def test_delete_unused_skill_removes_source_but_keeps_immutable_blobs(api_client):
    skill = imported(api_client)
    service = api_client.app.state.skills
    assert api_client.delete(f"/api/skills/{skill['id']}").status_code == 204
    assert not (service.library.root / "table-report").exists()
    assert sync(api_client)["items"] == []
    assert service.read_blob(skill["files"][0]["content_hash"])


def test_standard_creation_defaults_to_original_name_and_alias_can_be_reset(api_client):
    response = api_client.post("/api/skills", json={"skill_md": SOURCE})
    assert response.status_code == 201, response.text
    skill = response.json()
    assert skill["name"] == "table-report"
    renamed = api_client.patch(
        f"/api/skills/{skill['id']}",
        json={"expected_revision": skill["revision"], "name": "表格报告"},
    ).json()
    reset = api_client.patch(
        f"/api/skills/{skill['id']}", json={"expected_revision": renamed["revision"], "name": None}
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["name"] == "table-report"
    assert reset.json()["source_path"] == "table-report"
