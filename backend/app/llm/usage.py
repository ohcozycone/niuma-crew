"""Provider-reported token counts and conservative accumulation across model calls."""

from typing import Any, Mapping

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
    return {
        key: (
            totals.get(key, 0) + current[key]
            if current
            and current.get(key) is not None
            and (count == 1 or totals.get(key) is not None)
            else None
        )
        for key in TokenUsage.model_fields
    }
