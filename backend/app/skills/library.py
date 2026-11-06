"""Editable portable directories; published manifests remain the runtime source.

The file lock serializes platform writers across processes. External installers do
not share that lock, so writes also compare the current bytes with the last source
manifest. A database failure restores the prior directory before releasing it.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.errors import ConflictError
from app.skills.packages import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_PACKAGE_BYTES,
    package_error,
    validate_files,
)


def fingerprint(files: dict[str, bytes]) -> str:
    return hashlib.sha256(
        json.dumps(
            [[path, hashlib.sha256(body).hexdigest()] for path, body in sorted(files.items())],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


class SkillLibrary:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    @contextmanager
    def locked(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.root / ".platform.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def path(self, name: str) -> Path:
        if (
            not name
            or Path(name).name != name
            or name.startswith(".")
            or "/" in name
            or "\\" in name
        ):
            raise package_error("技能源目录名称无效。")
        destination = self.root / name
        if destination.is_symlink():
            raise package_error("技能目录不能是符号链接；请安装实际文件到配置的技能目录。")
        return destination

    def read(self, name: str) -> dict[str, bytes]:
        source = self.path(name)
        if not source.is_dir():
            raise package_error("技能源目录不存在，请恢复目录后同步。")
        files: dict[str, bytes] = {}
        total = directories = 0
        for parent, folders, names in os.walk(source, followlinks=False):
            directories += 1
            if directories > 256:
                raise package_error("技能目录层级或目录数量超过上限。")
            for child in folders:
                if (Path(parent) / child).is_symlink():
                    raise package_error("技能包不允许符号链接。")
            for child in names:
                path = Path(parent) / child
                relative = path.relative_to(source).as_posix()
                if len(files) >= MAX_FILES:
                    raise package_error("技能包最多 128 个文件。")
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(fd, "rb") as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                            raise package_error("技能包不允许特殊文件。")
                        body = stream.read(MAX_FILE_BYTES + 1)
                except OSError:
                    raise package_error("无法读取技能文件，请检查文件权限及链接。") from None
                total += len(body)
                if total > MAX_PACKAGE_BYTES or len(body) > MAX_FILE_BYTES:
                    raise package_error("技能包大小超过上限。")
                files[relative] = body
        metadata = validate_files(files)
        if metadata["name"] != name:
            raise package_error("技能目录名必须与 SKILL.md 的 name 一致。")
        return files

    def names(self) -> list[str]:
        if not self.root.exists():
            return []
        entries = list(self.root.iterdir())
        if len(entries) > 2000:
            raise package_error("技能库目录数量超过上限。")
        return sorted(
            path.name
            for path in entries
            if not path.name.startswith(".")
            and (path.is_symlink() or (path.is_dir() and (path / "SKILL.md").exists()))
        )

    @contextmanager
    def replace(
        self, name: str, files: dict[str, bytes] | None, expected: str | None
    ) -> Iterator[None]:
        destination = self.path(name)
        exists = destination.exists()
        if exists:
            if expected is None or fingerprint(self.read(name)) != expected:
                raise ConflictError(
                    "skill_source_changed", "技能目录已存在或被外部修改，请先同步后核对。"
                )
        elif expected is not None and files is not None:
            raise ConflictError("skill_source_missing", "技能源目录已移除，请恢复后同步。")
        temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=self.root))
        backup = temporary / "previous"
        staged = temporary / "next"
        installed = False
        try:
            if files is not None:
                staged.mkdir(mode=0o700)
                for relative, body in files.items():
                    target = staged / relative
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    with target.open("xb") as stream:
                        os.chmod(target, 0o600)
                        stream.write(body)
                        stream.flush()
                        os.fsync(stream.fileno())
            if exists:
                destination.rename(backup)
            if files is not None:
                staged.rename(destination)
                installed = True
            yield
        except BaseException:
            if installed and destination.exists():
                shutil.rmtree(destination)
            if backup.exists():
                backup.rename(destination)
            raise
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
