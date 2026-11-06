"""Provider-reported token counts and conservative accumulation across model calls."""

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
    """Keep incomplete cumulative fields unknown, including unreported failed calls."""

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
