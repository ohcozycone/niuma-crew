from dataclasses import fields
from math import isfinite
from typing import Any, get_type_hints


def validate_positive(settings: Any) -> None:
    annotations = get_type_hints(type(settings))
    for field in fields(settings):
        if field.name == "enabled":
            continue
        value = getattr(settings, field.name)
        key = "RUN_" + field.name.upper()
        if annotations.get(field.name, field.type) is int:
            if type(value) is not int or value <= 0:
                raise ValueError(f"{key} 必须为正整数。")
        elif (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{key} 必须为有限正数。")


def positive_values(cls: Any, values: dict[str, str | None]) -> dict:
    kwargs = {}
    annotations = get_type_hints(cls)
    for field in fields(cls):
        key = "RUN_" + field.name.upper()
        if field.name == "enabled" or key not in values:
            continue
        try:
            kwargs[field.name] = (int if annotations.get(field.name, field.type) is int else float)(
                values[key]
            )
        except (ValueError, TypeError):
            raise ValueError(f"{key} 格式错误。") from None
    return kwargs
