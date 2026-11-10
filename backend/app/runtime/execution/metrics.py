from __future__ import annotations


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
