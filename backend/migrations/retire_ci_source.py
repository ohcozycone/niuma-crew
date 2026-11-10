"""Inventory or archive only the fixed CI Skill source before the 0012 upgrade.

Run with explicit paths after stopping all application and external Skill writers.
This command never loads application configuration, changes SQLite, or touches the
content-addressed blob store. A manifest is durable before the final source rename.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing, nullcontext
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.errors import ServiceError
from app.skills.definitions import definition_from_record
from app.skills.library import SkillLibrary, fingerprint
from app.skills.packages import checked_package_path

CI_SKILL_ID = "6e69bf0e-84ca-44fd-8afb-d299a63d4381"


class ArchiveError(Exception):
    """Refuse an ambiguous path, unverified source or conflicting backup."""


def explicit_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise ArchiveError("请使用不包含上级跳转的绝对路径。")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ArchiveError("数据库、来源库和归档路径不能经过符号链接。")
    return path


def directory_path(value: str | Path) -> Path:
    path = explicit_path(value)
    if path.exists() and not path.is_dir():
        raise ArchiveError("来源库和归档的目录位置不能被普通文件占用。")
    return path


def database_path(database_url: str) -> Path:
    try:
        url = make_url(database_url)
    except ArgumentError:
        raise ArchiveError("database-url 必须是明确的文件型 SQLite URL。") from None
    if (
        url.drivername not in {"sqlite", "sqlite+pysqlite"}
        or not url.database
        or url.database == ":memory:"
        or url.host
        or url.username
        or url.password
        or url.query
    ):
        raise ArchiveError("归档工具只接受无额外参数的文件型 SQLite URL。")
    path = explicit_path(url.database)
    if not path.is_file():
        raise ArchiveError("指定数据库不存在；工具不会创建数据库。")
    return path


def read_record(database: Path) -> dict | None:
    uri = "file:" + quote(str(database), safe="/") + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        record = db.execute("SELECT * FROM skills WHERE id=?", (CI_SKILL_ID,)).fetchone()
    if record is None:
        return None
    result = dict(record)
    if not {"source_path", "skill_md", "package_manifest"} <= result.keys():
        raise ArchiveError("请先迁移到 0011，再盘点来源并执行 0012；当前缺少技能源字段。")
    for key in ("configuration_schema", "package_manifest"):
        try:
            result[key] = json.loads(result[key])
        except (TypeError, ValueError):
            raise ArchiveError("技能元数据格式无法确认，请从备份核对。") from None
    return result


def published_manifest(record: dict) -> tuple[dict[str, dict], str]:
    # There is no source_fingerprint column. Derive it from the published manifest,
    # using the same sorted path/hash pairs as SkillLibrary.fingerprint.
    definition = definition_from_record(SimpleNamespace(**record))
    manifest = definition.package_manifest
    expected: dict[str, dict] = {}
    if not isinstance(manifest, list):
        raise ArchiveError("已发布文件清单无法确认。")
    for item in manifest:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("content_hash"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", item["content_hash"])
            or type(item.get("size")) is not int
            or item["size"] < 0
        ):
            raise ArchiveError("已发布文件清单缺少有效的路径、摘要或大小。")
        name = checked_package_path(item["path"])
        if name in expected:
            raise ArchiveError("已发布文件清单存在重复路径。")
        expected[name] = item
    main = definition.skill_md.encode()
    if (
        "SKILL.md" not in expected
        or expected["SKILL.md"]["content_hash"] != hashlib.sha256(main).hexdigest()
        or expected["SKILL.md"]["size"] != len(main)
    ):
        raise ArchiveError("已发布正文与文件清单不一致，不能自动归档。")
    source_fingerprint = hashlib.sha256(
        json.dumps(
            [[path, item["content_hash"]] for path, item in sorted(expected.items())],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    return expected, source_fingerprint


def verify_source(library: SkillLibrary, name: str, expected: dict, expected_hash: str) -> None:
    files = library.read(name)
    if set(files) != set(expected) or any(
        len(body) != expected[path]["size"]
        or hashlib.sha256(body).hexdigest() != expected[path]["content_hash"]
        for path, body in files.items()
    ):
        raise ArchiveError("来源目录被外部修改或与已发布版本不同，请核对后重试。")
    if fingerprint(files) != expected_hash:
        raise ArchiveError("来源指纹与已发布版本不一致。")


def checked_backup(path: Path, manifest: dict) -> bool:
    if path.is_symlink():
        raise ArchiveError("归档清单不能是符号链接。")
    if not path.exists():
        return False
    try:
        previous = json.loads(path.read_text())
    except (OSError, ValueError):
        raise ArchiveError("既有归档清单不可读，不能覆盖。") from None
    if previous != manifest:
        raise ArchiveError("归档位置已有不同版本的清单，请使用新的外部归档目录。")
    return True


def save_backup(path: Path, manifest: dict) -> None:
    if checked_backup(path, manifest):
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    explicit_path(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".manifest-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            checked_backup(path, manifest)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def retire_ci_source(
    database_url: str,
    library_directory: str | Path,
    archive_directory: str | Path,
    *,
    apply: bool = False,
) -> dict:
    database = database_path(database_url)
    library_root = directory_path(library_directory)
    archive_root = directory_path(archive_directory)
    if archive_root == library_root or archive_root.is_relative_to(library_root):
        raise ArchiveError("归档目录必须在技能扫描根目录之外。")
    record = read_record(database)
    if record is None:
        return {
            "status": "skill_absent",
            "applied": False,
            "skill_id": CI_SKILL_ID,
            "message": "未找到固定技能记录；可能未安装或已退役，不能据此证明旧来源已归档。请核对升级前的备份。",
        }
    if not library_root.is_dir() and record["source_path"] is not None:
        return {
            "status": "source_missing",
            "applied": False,
            "skill_id": CI_SKILL_ID,
            "source_path": record["source_path"],
            "message": "来源库不存在；工具不会创建替代来源或按名称搜索其他目录。",
        }
    library = SkillLibrary(library_root)
    # A metadata-only record needs no source lock when the entire source library
    # is absent. In particular, inventory must not create an empty scanning root.
    with library.locked() if library_root.is_dir() else nullcontext():
        record = read_record(database)
        if record is None:
            raise ArchiveError("盘点期间技能记录被移除，请停止写入并核对。")
        name = record["source_path"]
        if name is not None and (not isinstance(name, str) or not name):
            raise ArchiveError("数据库中的来源目录名称无效。")
        if name is not None and not library_root.is_dir():
            raise ArchiveError("盘点期间来源指针发生变化且来源库不存在，请停止写入并核对。")
        expected, source_hash = published_manifest(record) if name else ({}, None)
        operation_root = directory_path(archive_root / CI_SKILL_ID)
        backup_path = operation_root / "manifest.json"
        manifest = {
            "format_version": 1,
            "skill_id": CI_SKILL_ID,
            "library_directory": str(library_root),
            "source_path": name,
            "source_fingerprint": source_hash,
            "record": record,
        }
        report = {
            "skill_id": CI_SKILL_ID,
            "source_path": name,
            "source_fingerprint": source_hash,
            "manifest_path": str(backup_path),
            "applied": False,
        }
        if name is None:
            if apply:
                save_backup(backup_path, manifest)
            return {**report, "status": "metadata_only", "applied": apply}
        source = library.path(name)
        archived_root = directory_path(operation_root / "source")
        destination = archived_root / name
        directory_path(destination)
        if source.exists() and destination.exists():
            raise ArchiveError("原目录和归档目录同时存在，工具不会覆盖或合并，请核对。")
        if not source.exists():
            if not destination.exists():
                return {
                    **report,
                    "status": "source_missing",
                    "message": "原来源和匹配归档均不存在。",
                }
            if not checked_backup(backup_path, manifest):
                raise ArchiveError("已有归档缺少匹配的元数据清单。")
            verify_source(SkillLibrary(archived_root), name, expected, source_hash)
            return {**report, "status": "already_archived", "archive_path": str(destination)}
        verify_source(library, name, expected, source_hash)
        checked_backup(backup_path, manifest)
        if not apply:
            return {**report, "status": "ready", "archive_path": str(destination)}
        if read_record(database) != record:
            raise ArchiveError("读取期间数据库记录发生变化，请停止写入后重试。")
        nearest_parent = archive_root
        while not nearest_parent.exists():
            nearest_parent = nearest_parent.parent
        if source.stat().st_dev != nearest_parent.stat().st_dev:
            raise ArchiveError("请选同一文件系统上的外部归档目录，以便原子移动来源。")
        save_backup(backup_path, manifest)
        archived_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory_path(archived_root)
        if directory_path(destination).exists():
            raise ArchiveError("归档目标在校验后出现，工具不会覆盖，请核对后重试。")
        # All verification and durable metadata writes precede the rename. A failed
        # move leaves the original directory intact; its matching manifest is reusable.
        source.rename(destination)
        return {**report, "status": "archived", "applied": True, "archive_path": str(destination)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="停写并备份后，盘点或精确归档固定 CI 技能源。")
    parser.add_argument("--database-url", required=True, help="明确的绝对文件型 SQLite URL")
    parser.add_argument("--library-directory", required=True, help="技能扫描根目录的绝对路径")
    parser.add_argument("--archive-directory", required=True, help="扫描根目录之外的归档绝对路径")
    parser.add_argument("--apply", action="store_true", help="执行归档；默认仅盘点和校验")
    args = parser.parse_args(argv)
    try:
        result = retire_ci_source(
            args.database_url, args.library_directory, args.archive_directory, apply=args.apply
        )
    except (ArchiveError, ServiceError) as error:
        result = {"status": "blocked", "applied": False, "message": str(error)}
    except (OSError, sqlite3.Error, ValueError):
        result = {
            "status": "blocked",
            "applied": False,
            "message": "文件或数据库操作失败；请核对路径、权限和磁盘，工具不会删除来源内容。",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] in {"blocked", "source_missing"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
