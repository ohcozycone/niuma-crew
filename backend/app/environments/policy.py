from __future__ import annotations

import posixpath

from app.errors import InvalidInputError, PermissionDeniedError

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


def authorize_workspace_arguments(binding: dict, arguments: dict) -> None:
    scope, name = (binding["scope_policy"], binding["tool_name"])
    if name == "execute":
        if (
            not isinstance(arguments.get("command"), str)
            or not arguments["command"].strip()
            or len(arguments["command"].encode()) > 16384
        ):
            raise InvalidInputError("tool_arguments_invalid", "执行命令为空或超过长度限制。")
        return
    path = checked_path(arguments.get("file_path", arguments.get("path", "/")))
    roots = scope.get("write_roots" if name in WRITE_TOOLS else "read_roots", [])
    if path == "/" and name in ("ls", "glob", "grep"):
        if not roots:
            raise PermissionDeniedError("file_path_denied", "未授予文件读取范围。")
    elif not any((under(path, root) for root in roots)):
        raise PermissionDeniedError("file_path_denied", "文件路径不在本轮许可范围内。")
