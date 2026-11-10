from typing import Any, Mapping

from langchain_core.messages.ai import UsageMetadata, add_usage
from pydantic import BaseModel


class TokenUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None


def parse_token_usage(usage: Mapping[str, Any] | None) -> TokenUsage | None:
    if not usage:
        return None
    return TokenUsage(
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        total_tokens=usage.get("total_tokens"),
        cached_input_tokens=usage.get("input_token_details", {}).get("cache_read"),
        reasoning_tokens=usage.get("output_token_details", {}).get("reasoning"),
    )


def aggregate_usage(
    totals: dict[str, int | None], current: dict[str, int | None] | None, count: int
) -> dict[str, int | None]:
    """任一次调用未报告的用量字段，累计值也保持未知。"""

    def known(values: dict[str, int | None]) -> UsageMetadata:
        return UsageMetadata(
            input_tokens=values.get("input_tokens") or 0,
            output_tokens=values.get("output_tokens") or 0,
            total_tokens=values.get("total_tokens") or 0,
            input_token_details={"cache_read": values.get("cached_input_tokens") or 0},
            output_token_details={"reasoning": values.get("reasoning_tokens") or 0},
        )

    combined = parse_token_usage(add_usage(known(totals), known(current or {})))
    assert combined is not None
    return {
        key: (
            getattr(combined, key)
            if current
            and current.get(key) is not None
            and (count == 1 or totals.get(key) is not None)
            else None
        )
        for key in TokenUsage.model_fields
    }


def diagnostic_metrics(sent: dict, received: dict, recorded_usage: dict | None) -> dict:
    """从已采集的请求和用量生成指标，不以当前配置推断历史。"""
    usage = received.get("usage")
    source = "response"
    if not isinstance(usage, dict) or not usage:
        usage = recorded_usage
        source = "action"
    usage = usage if isinstance(usage, dict) else {}
    output_details = usage.get("output_token_details")
    reasoning = output_details.get("reasoning") if isinstance(output_details, dict) else None

    def count(value):
        return value if type(value) is int and value >= 0 else None

    limit_field = "max_completion_tokens" if "max_completion_tokens" in sent else "max_tokens"
    return {
        "usage": {
            **{
                key: count(usage.get(key))
                for key in ("input_tokens", "output_tokens", "total_tokens")
            },
            "reasoning_tokens": count(usage.get("reasoning_tokens", reasoning)),
        },
        "usage_source": source if usage else None,
        "output_limit": count(sent.get(limit_field)),
        "output_limit_field": limit_field if count(sent.get(limit_field)) is not None else None,
    }
