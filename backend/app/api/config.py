from dataclasses import dataclass

from app.infrastructure.settings import positive_values, validate_positive


@dataclass(frozen=True)
class StreamConfig:
    poll_interval: float = 0.5  # SSE 快照轮询间隔，秒。
    auth_interval: float = 5  # 订阅期间的身份与权限复核间隔，秒。
    subscription_limit: int = 4  # 每账号上限。
    subscription_seconds: float = 300

    def __post_init__(self) -> None:
        validate_positive(self)


def load_stream_config(values: dict[str, str | None]) -> StreamConfig:
    return StreamConfig(**positive_values(StreamConfig, values))
