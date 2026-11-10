from app.common.usage import TokenUsage


def aggregate_usage(
    totals: dict[str, int | None], current: dict[str, int | None] | None, count: int
) -> dict[str, int | None]:
    """累计规范化的用量；任一次未报告的字段继续保持未知。"""
    return {
        key: (
            int(totals.get(key) or 0) + int(current[key])
            if current
            and current.get(key) is not None
            and (count == 1 or totals.get(key) is not None)
            else None
        )
        for key in TokenUsage.model_fields
    }
