"""Bounded, local JSON Schema validation for non-secret assembly parameters."""

import json

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from app.errors import InvalidInputError


def json_size(value):
    try:
        return len(json.dumps(value, allow_nan=False).encode())
    except (ValueError, TypeError, RecursionError):
        raise ValueError("配置必须为有限、有效的 JSON 值。") from None


def validate_schema(schema):
    if not isinstance(schema, dict) or json_size(schema) > 16384:
        raise ValueError("参数规范必须为不超过 16 KiB 的 JSON 对象。")
    if schema and (
        schema.get("type") != "object" or schema.get("additionalProperties") is not False
    ):
        raise ValueError("参数规范根必须为 object，且 additionalProperties=false。")

    def visit(value, depth=0):
        if depth > 20:
            raise ValueError("参数规范嵌套过深。")
        if isinstance(value, dict):
            if any(key in value for key in ("$ref", "$dynamicRef", "$id")):
                raise ValueError("参数规范不允许引用或远程资源。")
            for child in value.values():
                visit(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                visit(child, depth + 1)

    visit(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise ValueError("参数规范不是有效的 JSON Schema。") from None
    return schema


def validate_parameters(schema, parameters):
    try:
        size = json_size(parameters)
    except ValueError:
        size = 16385
    if not isinstance(parameters, dict) or size > 16384:
        raise InvalidInputError(
            "skill_parameters_invalid", "技能参数必须为不超过 16 KiB 的 JSON 对象。"
        )
    try:
        if not schema and parameters:
            raise ValidationError("Empty schema permits empty parameters only")
        Draft202012Validator(schema).validate(parameters)
    except (ValidationError, RecursionError):
        # Never echo parameter values; secrets must not enter this configuration surface.
        raise InvalidInputError(
            "skill_parameters_invalid", "技能参数不符合当前规范，请检查类型、必填项及未知字段。"
        ) from None
