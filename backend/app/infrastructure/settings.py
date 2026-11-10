from dataclasses import fields
from math import isfinite
from typing import Any


def validate_positive(settings: Any) -> None:
    for field in fields(settings):
        if field.name == "enabled":
            continue
        value = getattr(settings, field.name)
        key = "RUN_" + field.name.upper()
        if field.type is int:
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
    for field in fields(cls):
        key = "RUN_" + field.name.upper()
        if field.name == "enabled" or key not in values:
            continue
        try:
            kwargs[field.name] = (int if field.type is int else float)(values[key])
        except (ValueError, TypeError):
            raise ValueError(f"{key} 格式错误。") from None
    return kwargs
