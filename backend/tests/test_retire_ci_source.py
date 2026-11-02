"""Exercise the upgrade-only source archive against isolated 0011 databases."""

import fcntl
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from test_ci_retirement import insert
from test_ci_retirement import retirement_database as retirement_database

from app.errors import ServiceError
from app.skills.library import SkillLibrary, fingerprint
from app.skills.packages import file_manifest
from migrations import retire_ci_source as retirement


@pytest.fixture
def ci_source(retirement_database):
    fixture = retirement_database
    library = fixture.directory / "library"
    library.mkdir()
    name = "old-review-method"
    source = library / name
    source.mkdir()
    files = {
        "SKILL.md": (
            f"---\nname: {name}\ndescription: An old experiment\n---\nCheck the evidence.\n"
        ).encode(),
        "references/method.txt": b"Historical method content\n",
    }
    for relative, body in files.items():
        path = source / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(body)
    with closing(sqlite3.connect(fixture.path)) as db:
        insert(
            db,
            "skills",
            id=retirement.CI_SKILL_ID,
            name="The fixed retired experiment",
            skill_md=files["SKILL.md"].decode(),
            source_path=name,
            package_manifest=json.dumps(
                [file_manifest(path, body) for path, body in files.items()]
            ),
            configuration_schema=json.dumps({"properties": {"example": {"type": "string"}}}),
        )
        # A name containing CI never makes another Skill eligible for retirement.
        insert(db, "skills", id=str(uuid4()), name="CI diagnosis user method")
        db.commit()
    ordinary = library / "ci-diagnosis-user-method"
    ordinary.mkdir()
    (ordinary / "SKILL.md").write_text("This is an unrelated user directory.")
    blobs = fixture.directory / "skill-blobs"
    blobs.mkdir()
    (blobs / "keep").write_bytes(b"Historical immutable content")
    return SimpleNamespace(
        **vars(fixture),
        url="sqlite+pysqlite:///" + str(fixture.path),
        library=library,
        source=source,
        files=files,
        archive=fixture.directory / "archive",
        ordinary=ordinary,
        blobs=blobs,
    )


def run(fixture, *, apply=False):
    return retirement.retire_ci_source(fixture.url, fixture.library, fixture.archive, apply=apply)


def test_inventory_is_locked_and_does_not_move_or_change_database(ci_source, monkeypatch):
    before = ci_source.path.read_bytes()
    original_read = SkillLibrary.read
    checked = []

    def no_application_configuration(*args, **kwargs):
        raise AssertionError("The upgrade-only tool must not load configuration or .env")

    monkeypatch.setattr("app.config._read_values", no_application_configuration)

    def read_locked(library, name):
        with (ci_source.library / ".platform.lock").open("rb") as lock:
            with pytest.raises(BlockingIOError):
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        checked.append(name)
        return original_read(library, name)

    monkeypatch.setattr(SkillLibrary, "read", read_locked)
    result = run(ci_source)
    assert result["status"] == "ready"
    assert result["applied"] is False
    assert result["source_fingerprint"] == fingerprint(ci_source.files)
    assert checked == [ci_source.source.name]
    assert not ci_source.archive.exists()
    assert ci_source.path.read_bytes() == before
    assert original_read(SkillLibrary(ci_source.library), ci_source.source.name) == ci_source.files


def test_apply_backs_up_all_metadata_and_moves_only_exact_source(ci_source):
    before = ci_source.path.read_bytes()
    result = run(ci_source, apply=True)
    assert result["status"] == "archived"
    assert result["applied"] is True
    assert not ci_source.source.exists()
    destination = Path(result["archive_path"])
    assert not destination.is_relative_to(ci_source.library)
    assert SkillLibrary(destination.parent).read(destination.name) == ci_source.files
    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text())
    assert manifest["record"] == retirement.read_record(ci_source.path)
    assert manifest["source_fingerprint"] == fingerprint(ci_source.files)
    assert manifest["record"]["source_path"] == ci_source.source.name
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert manifest_path.parent.stat().st_mode & 0o777 == 0o700
    assert ci_source.path.read_bytes() == before
    assert (ci_source.ordinary / "SKILL.md").read_text() == "This is an unrelated user directory."
    assert (ci_source.blobs / "keep").read_bytes() == b"Historical immutable content"
    assert run(ci_source, apply=True)["status"] == "already_archived"
    assert run(ci_source)["status"] == "already_archived"


@pytest.mark.parametrize("change", ["modified", "extra", "missing"])
def test_source_drift_blocks_apply_before_any_archive_write(ci_source, change):
    support = ci_source.source / "references/method.txt"
    if change == "modified":
        support.write_bytes(b"Externally edited method")
    elif change == "extra":
        (ci_source.source / "extra.txt").write_bytes(b"Unexpected extra file")
    else:
        support.unlink()
    with pytest.raises(retirement.ArchiveError, match="外部修改"):
        run(ci_source, apply=True)
    assert ci_source.source.exists()
    assert not ci_source.archive.exists()


@pytest.mark.parametrize("location", ["library", "source", "file", "archive", "manifest"])
def test_links_are_rejected_without_following_or_moving_target(ci_source, location):
    target = ci_source.directory / "link-target"
    if location == "library":
        ci_source.library.rename(target)
        ci_source.library.symlink_to(target, target_is_directory=True)
    elif location == "source":
        ci_source.source.rename(target)
        ci_source.source.symlink_to(target, target_is_directory=True)
    elif location == "file":
        support = ci_source.source / "references/method.txt"
        support.rename(target)
        support.symlink_to(target)
    elif location == "archive":
        target.mkdir()
        ci_source.archive.symlink_to(target, target_is_directory=True)
    else:
        (ci_source.archive / retirement.CI_SKILL_ID).mkdir(parents=True)
        target.write_text("Unrelated existing file")
        (ci_source.archive / retirement.CI_SKILL_ID / "manifest.json").symlink_to(target)
    with pytest.raises((retirement.ArchiveError, ServiceError), match="链接"):
        run(ci_source, apply=True)
    assert target.exists()
    if location in {"library", "source"}:
        assert (
            target / (ci_source.source.name if location == "library" else "") / "SKILL.md"
        ).exists()
    if location == "manifest":
        assert target.read_text() == "Unrelated existing file"


@pytest.mark.parametrize("path", ["../external", "/external", ".hidden", "nested/source"])
def test_database_source_path_cannot_escape_scanning_root(ci_source, path):
    with closing(sqlite3.connect(ci_source.path)) as db:
        db.execute("UPDATE skills SET source_path=? WHERE id=?", (path, retirement.CI_SKILL_ID))
        db.commit()
    with pytest.raises((retirement.ArchiveError, ServiceError)):
        run(ci_source, apply=True)
    assert ci_source.source.exists()
    assert not ci_source.archive.exists()


@pytest.mark.parametrize("relative", [".", "archive"])
def test_archive_directory_must_be_outside_scanning_root(ci_source, relative):
    ci_source.archive = ci_source.library / relative
    with pytest.raises(retirement.ArchiveError, match="扫描根目录之外"):
        run(ci_source, apply=True)
    assert ci_source.source.exists()


def test_rename_failure_preserves_original_and_can_resume_from_manifest(ci_source, monkeypatch):
    original = Path.rename

    def fail_move(path, destination):
        if path == ci_source.source:
            raise OSError("injected rename failure")
        return original(path, destination)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", fail_move)
        with pytest.raises(OSError, match="injected"):
            run(ci_source, apply=True)
    assert SkillLibrary(ci_source.library).read(ci_source.source.name) == ci_source.files
    manifest = ci_source.archive / retirement.CI_SKILL_ID / "manifest.json"
    assert json.loads(manifest.read_text())["record"]["id"] == retirement.CI_SKILL_ID
    assert run(ci_source, apply=True)["status"] == "archived"


def test_cross_filesystem_archive_is_rejected_before_writing_backup(ci_source, monkeypatch):
    original = Path.stat

    def stat_on_another_device(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        if path == ci_source.source:
            fields = list(value)
            fields[2] += 1  # st_dev; keep all file type and permission bits intact.
            return os.stat_result(fields)
        return value

    monkeypatch.setattr(Path, "stat", stat_on_another_device)
    with pytest.raises(retirement.ArchiveError, match="同一文件系统"):
        run(ci_source, apply=True)
    assert ci_source.source.exists()
    assert not ci_source.archive.exists()


@pytest.mark.parametrize("location", ["archive", "operation", "source"])
def test_existing_file_cannot_be_reported_as_ready_archive_directory(ci_source, location):
    location_path = ci_source.archive
    if location in {"operation", "source"}:
        location_path /= retirement.CI_SKILL_ID
    if location == "source":
        location_path /= "source"
    location_path.parent.mkdir(parents=True, exist_ok=True)
    location_path.write_text("Keep this unrelated file")
    with pytest.raises(retirement.ArchiveError, match="普通文件占用"):
        run(ci_source)
    assert location_path.read_text() == "Keep this unrelated file"
    assert ci_source.source.exists()


def test_reentry_validates_archived_bytes(ci_source):
    result = run(ci_source, apply=True)
    support = Path(result["archive_path"]) / "references/method.txt"
    support.write_text("Changed since archive")
    with pytest.raises(retirement.ArchiveError, match="外部修改"):
        run(ci_source, apply=True)
    assert support.read_text() == "Changed since archive"


def test_conflicting_or_missing_backups_are_never_overwritten(ci_source):
    run(ci_source, apply=True)
    root = ci_source.archive / retirement.CI_SKILL_ID
    backup = root / "manifest.json"
    backup.write_text('{"unrelated": true}')
    with pytest.raises(retirement.ArchiveError, match="不同版本"):
        run(ci_source, apply=True)
    assert json.loads(backup.read_text()) == {"unrelated": True}
    backup.unlink()
    with pytest.raises(retirement.ArchiveError, match="缺少匹配"):
        run(ci_source, apply=True)
    assert (root / "source" / ci_source.source.name / "SKILL.md").exists()


def test_metadata_changes_before_apply_block_moving_verified_source(ci_source, monkeypatch):
    original = retirement.read_record
    reads = 0

    def changing_record(database):
        nonlocal reads
        reads += 1
        record = original(database)
        if reads == 3:
            record["revision"] += 1
        return record

    monkeypatch.setattr(retirement, "read_record", changing_record)
    with pytest.raises(retirement.ArchiveError, match="记录发生变化"):
        run(ci_source, apply=True)
    assert ci_source.source.exists()
    assert not ci_source.archive.exists()


def test_missing_sources_and_removed_metadata_are_not_reported_as_archived(ci_source):
    held = ci_source.directory / "held-source"
    ci_source.source.rename(held)
    assert run(ci_source, apply=True)["status"] == "source_missing"
    assert not ci_source.archive.exists()
    held.rename(ci_source.source)
    result = run(ci_source, apply=True)
    command.upgrade(ci_source.configuration, "head")
    after_upgrade = run(ci_source, apply=True)
    assert after_upgrade["status"] == "skill_absent"
    assert after_upgrade["applied"] is False
    assert "不能据此证明" in after_upgrade["message"]
    assert Path(result["archive_path"]).is_dir()
    assert ci_source.ordinary.exists()


def test_record_without_source_only_backs_up_metadata(ci_source):
    with closing(sqlite3.connect(ci_source.path)) as db:
        db.execute("UPDATE skills SET source_path=NULL WHERE id=?", (retirement.CI_SKILL_ID,))
        db.commit()
    assert run(ci_source)["status"] == "metadata_only"
    assert not ci_source.archive.exists()
    result = run(ci_source, apply=True)
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["source_path"] is None
    assert manifest["source_fingerprint"] is None
    assert ci_source.source.exists()
    assert ci_source.ordinary.exists()


def test_metadata_only_record_never_creates_missing_library(ci_source):
    with closing(sqlite3.connect(ci_source.path)) as db:
        db.execute("UPDATE skills SET source_path=NULL WHERE id=?", (retirement.CI_SKILL_ID,))
        db.commit()
    ci_source.library.rename(ci_source.directory / "held-library")
    assert run(ci_source)["status"] == "metadata_only"
    assert not ci_source.library.exists()
    assert not ci_source.archive.exists()
    result = run(ci_source, apply=True)
    assert result["status"] == "metadata_only"
    assert not ci_source.library.exists()
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["source_path"] is None
    assert manifest["record"] == retirement.read_record(ci_source.path)


def test_source_pointer_with_missing_library_stays_blocked(ci_source, capsys):
    ci_source.library.rename(ci_source.directory / "held-library")
    assert (
        retirement.main(
            [
                "--database-url",
                ci_source.url,
                "--library-directory",
                str(ci_source.library),
                "--archive-directory",
                str(ci_source.archive),
                "--apply",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "source_missing"
    assert not ci_source.library.exists()
    assert not ci_source.archive.exists()


def test_cli_requires_explicit_arguments_and_defaults_to_inventory(ci_source, capsys):
    with pytest.raises(SystemExit) as missing:
        retirement.main([])
    assert missing.value.code == 2
    arguments = [
        "--database-url",
        ci_source.url,
        "--library-directory",
        str(ci_source.library),
        "--archive-directory",
        str(ci_source.archive),
    ]
    assert retirement.main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
    assert ci_source.source.exists()
    assert retirement.main([*arguments, "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "archived"
    assert not ci_source.source.exists()


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///:memory:",
        "sqlite:///relative.db",
        "postgresql://user:secret@localhost/example",
        "sqlite+pysqlite:////missing/example.db",
    ],
)
def test_explicit_database_url_cannot_create_database_or_use_other_backends(ci_source, url):
    with pytest.raises(retirement.ArchiveError):
        retirement.retire_ci_source(url, ci_source.library, ci_source.archive, apply=True)
    assert ci_source.source.exists()
    assert not ci_source.archive.exists()
