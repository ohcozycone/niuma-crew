from dataclasses import dataclass

from app.infrastructure.settings import positive_values, validate_positive


@dataclass(frozen=True)
class AgentConfig:
    recursion_limit: int = 64  # 图步数上限，不等于模型或工具调用次数。
    max_output_tokens: int = 4096  # 每次模型调用的输出 token 上限。
    context_bytes: int = 131072  # 按序列化字节限制输入，不是 token 数。
    summary_trigger_tokens: int = 16384  # 以估算 token 数触发摘要。
    summary_keep_tokens: int = 4096  # 摘要后保留的近期消息 token 预算。

    def __post_init__(self) -> None:
        validate_positive(self)
        if self.summary_keep_tokens >= self.summary_trigger_tokens:
            raise ValueError("summary_keep_tokens must be less than summary_trigger_tokens")


def load_agent_config(values: dict[str, str | None]) -> AgentConfig:
    return AgentConfig(**positive_values(AgentConfig, values))
