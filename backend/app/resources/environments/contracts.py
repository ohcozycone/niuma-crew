import posixpath
from dataclasses import dataclass
from typing import Protocol

from app.common.errors import PermissionDeniedError

WRITE_TOOLS = frozenset({"write_file", "edit_file", "delete", "execute"})


def checked_path(path: str) -> str:
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or "\\" in path
        or ("\x00" in path)
        or (".." in path.split("/"))
    ):
        raise PermissionDeniedError("file_path_denied", "文件路径不在本轮许可范围内。")
    return posixpath.normpath(path)


def under(path: str, root: str) -> bool:
    return path == root.rstrip("/") or path.startswith(root.rstrip("/") + "/")


@dataclass(frozen=True)
class CommandResult:
    output: str
    exit_code: int


class SandboxFileOperations(Protocol):
    def execute(self, command: str, *, timeout: int | None = None) -> CommandResult: ...
    def materialize_readonly(self, files: list[tuple[str, bytes]]) -> None: ...
    def check_path(self, path: str, *, write: bool = False) -> None: ...
    def collect_outputs(self) -> list: ...
