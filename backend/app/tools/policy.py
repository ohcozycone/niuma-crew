"""Host-enforced scopes; schemas and model descriptions never grant access."""

import ipaddress
import posixpath
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, ValidationError

from app.errors import InvalidInputError, PermissionDeniedError
from app.tools.contracts import WRITE_TOOLS


def checked_path(path: str) -> str:
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or "\\" in path
        or "\x00" in path
        or ".." in path.split("/")
    ):
        raise PermissionDeniedError("file_path_denied", "文件路径不在本轮许可范围内。")
    return posixpath.normpath(path)


def under(path: str, root: str) -> bool:
    return path == root.rstrip("/") or path.startswith(root.rstrip("/") + "/")


def validate_scope(scope: dict, kind: str) -> None:
    allowed = {"mode", "max_calls", "arguments", "allowed_domains", "read_roots", "write_roots"}
    if set(scope) - allowed or scope.get("mode") != (
        "workspace" if kind == "native" else "provider"
    ):
        raise InvalidInputError(
            "tool_scope_invalid", "请选择明确的工作区范围或受限上游身份，不能使用空许可。"
        )
    if type(scope.get("max_calls", 32)) is not int or not 1 <= scope.get("max_calls", 32) <= 32:
        raise InvalidInputError("tool_scope_invalid", "单项工具调用上限必须为 1–32。")
    if kind == "native":
        for key, choices in (
            ("read_roots", ("/inputs", "/sources", "/workspace", "/outputs")),
            ("write_roots", ("/workspace", "/outputs")),
        ):
            roots = scope.get(key, [])
            if not isinstance(roots, list) or any(root not in choices for root in roots):
                raise InvalidInputError("tool_scope_invalid", "文件许可仅支持明确的预置目录。")
    else:
        rules = scope.get("arguments", {})
        if not isinstance(rules, dict) or any(
            not isinstance(rule, dict) or set(rule) - {"maximum", "maxItems", "maxLength", "enum"}
            for rule in rules.values()
        ):
            raise InvalidInputError("tool_scope_invalid", "工具参数限制包含未支持的规则。")
        for rule in rules.values():
            try:
                Draft202012Validator.check_schema(rule)
            except Exception:
                raise InvalidInputError("tool_scope_invalid", "工具参数限制格式无效。") from None
        domains = scope.get("allowed_domains", [])
        if not isinstance(domains, list) or any(
            not isinstance(d, str) or not d or "/" in d or ":" in d for d in domains
        ):
            raise InvalidInputError("tool_scope_invalid", "域名范围必须为不含协议和路径的域名。")


def authorize_arguments(binding: dict, arguments: dict) -> None:
    scope = binding["scope_policy"]
    if binding["kind"] == "native":
        name = binding["tool_name"]
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
        elif not any(under(path, root) for root in roots):
            raise PermissionDeniedError("file_path_denied", "文件路径不在本轮许可范围内。")
        return
    try:
        Draft202012Validator(binding["input_schema"]).validate(arguments)
        for key, rule in scope.get("arguments", {}).items():
            if key in arguments:
                Draft202012Validator(rule).validate(arguments[key])
    except ValidationError:
        raise InvalidInputError(
            "tool_arguments_invalid", "工具参数不符合已批准定义或许可限制。"
        ) from None
    # Page extraction is a distinct permission. Never forward authenticated URLs
    # or obvious private destinations to an internet extraction provider.
    urls = arguments.get("urls", [])
    if "url" in arguments:
        urls = [*urls, arguments["url"]] if isinstance(urls, list) else [arguments["url"]]
    if isinstance(urls, str):
        urls = [urls]
    if not isinstance(urls, list) or len(urls) > 3:
        raise InvalidInputError("tool_arguments_invalid", "每次最多读取三个网页。")
    domains = scope.get("allowed_domains", [])
    for value in urls:
        url = urlsplit(value)
        host = (url.hostname or "").lower()
        try:
            private = not ipaddress.ip_address(host).is_global
        except ValueError:
            private = (
                host in ("localhost",) or "." not in host or host.endswith((".local", ".internal"))
            )
        if (
            url.scheme not in ("http", "https")
            or url.username
            or url.password
            or private
            or (domains and not any(host == d or host.endswith("." + d) for d in domains))
        ):
            raise PermissionDeniedError("tool_url_denied", "网页地址不属于获准公开范围。")


def effective_arguments(binding: dict, arguments: dict) -> dict:
    result = dict(arguments)
    domains = binding["scope_policy"].get("allowed_domains", [])
    if binding["tool_name"] == "tavily_search":
        properties = binding["input_schema"].get("properties", {})
        if "max_results" in properties:
            result["max_results"] = min(result.get("max_results", 5), 5)
        for key in ("include_raw_content", "include_answer"):
            if key in properties:
                result[key] = False
        if domains:
            if "include_domains" not in properties:
                raise InvalidInputError("tool_scope_invalid", "当前搜索工具不能强制域名范围。")
            result["include_domains"] = domains
    return result
