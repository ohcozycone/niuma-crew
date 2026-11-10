from typing import Any, Mapping

from app.common.usage import TokenUsage


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
