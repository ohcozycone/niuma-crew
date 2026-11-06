"""Workspace path and native operation authorization."""

from __future__ import annotations

import posixpath

from app.environments.profiles import WRITE_TOOLS
from app.errors import InvalidInputError, PermissionDeniedError


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


def validate_workspace_scope(scope: dict) -> None:
    if (
        set(scope) - {"mode", "max_calls", "read_roots", "write_roots"}
        or scope.get("mode") != "workspace"
    ):
        raise InvalidInputError("tool_scope_invalid", "请选择明确的工作区范围。")
    if type(scope.get("max_calls", 32)) is not int or not 1 <= scope.get("max_calls", 32) <= 32:
        raise InvalidInputError("tool_scope_invalid", "单项工具调用上限必须为 1–32。")
    for key, choices in (
        ("read_roots", ("/inputs", "/sources", "/workspace", "/outputs")),
        ("write_roots", ("/workspace", "/outputs")),
    ):
        roots = scope.get(key, [])
        if not isinstance(roots, list) or any((root not in choices for root in roots)):
            raise InvalidInputError("tool_scope_invalid", "文件许可仅支持明确的预置目录。")


def authorize_workspace_arguments(binding: dict, arguments: dict) -> None:
    scope, name = (binding["scope_policy"], binding["tool_name"])
    if name == "execute":
        if (
            not isinstance(arguments.get("command"), str)
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
