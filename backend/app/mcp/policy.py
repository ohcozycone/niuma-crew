"""Host-enforced scopes; schemas and model descriptions never grant access."""

import ipaddress
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, ValidationError

from app.errors import InvalidInputError, PermissionDeniedError


def validate_scope(scope: dict, kind: str) -> None:
    allowed = {"mode", "max_calls", "arguments", "allowed_domains"}
    if set(scope) - allowed or scope.get("mode") != "provider":
        raise InvalidInputError(
            "tool_scope_invalid", "请选择明确的工作区范围或受限上游身份，不能使用空许可。"
        )
    if type(scope.get("max_calls", 32)) is not int or not 1 <= scope.get("max_calls", 32) <= 32:
        raise InvalidInputError("tool_scope_invalid", "单项工具调用上限必须为 1–32。")
    rules = scope.get("arguments", {})
    if not isinstance(rules, dict) or any(
        (
            not isinstance(rule, dict) or set(rule) - {"maximum", "maxItems", "maxLength", "enum"}
            for rule in rules.values()
        )
    ):
        raise InvalidInputError("tool_scope_invalid", "工具参数限制包含未支持的规则。")
    for rule in rules.values():
        try:
            Draft202012Validator.check_schema(rule)
        except Exception:
            raise InvalidInputError("tool_scope_invalid", "工具参数限制格式无效。") from None
    domains = scope.get("allowed_domains", [])
    if not isinstance(domains, list) or any(
        (not isinstance(d, str) or not d or "/" in d or (":" in d) for d in domains)
    ):
        raise InvalidInputError("tool_scope_invalid", "域名范围必须为不含协议和路径的域名。")


def authorize_arguments(binding: dict, arguments: dict) -> None:
    scope = binding["scope_policy"]
    try:
        Draft202012Validator(binding["input_schema"]).validate(arguments)
        for key, rule in scope.get("arguments", {}).items():
            if key in arguments:
                Draft202012Validator(rule).validate(arguments[key])
    except ValidationError:
        raise InvalidInputError(
            "tool_arguments_invalid", "工具参数不符合已批准定义或许可限制。"
        ) from None
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
            or (domains and (not any((host == d or host.endswith("." + d) for d in domains))))
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
