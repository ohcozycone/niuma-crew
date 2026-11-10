from jsonschema import Draft202012Validator, ValidationError

from app.errors import InvalidInputError


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
    if domains:
        raise InvalidInputError(
            "tool_scope_invalid",
            "当前通用 MCP 不支持隐式域名范围，请使用明确的参数约束或上游受限账号。",
        )


def authorize_arguments(binding: dict, arguments: dict) -> None:
    scope = binding["scope_policy"]
    validate_scope(scope, binding["kind"])
    try:
        Draft202012Validator(binding["input_schema"]).validate(arguments)
        for key, rule in scope.get("arguments", {}).items():
            if key in arguments:
                Draft202012Validator(rule).validate(arguments[key])
    except ValidationError:
        raise InvalidInputError(
            "tool_arguments_invalid", "工具参数不符合已批准定义或许可限制。"
        ) from None
