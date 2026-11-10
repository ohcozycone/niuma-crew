from dataclasses import dataclass

from app.infrastructure.settings import positive_values, validate_positive


@dataclass(frozen=True)
class RuntimeConfig:
    enabled: bool = True  # 仅供测试注入关闭，无对应环境变量。
    queue_capacity: int = 20
    per_user_capacity: int = 2  # 包含排队与执行中的 Run。
    queue_timeout: float = 30  # 秒。
    run_timeout: float = 180  # 秒。
    max_model_calls: int = 8
    max_skill_reads: int = 16  # 技能预加载与实际读取共用此预算。
    max_tool_calls: int = 32  # 包含实际技能读取；预加载只占技能预算。
    max_output_bytes: int = 131072  # 每轮及最终正文按 UTF-8 字节限制，超限停止。
    max_reasoning_bytes: int = 32768  # 每 Run 的 UTF-8 字节展示上限，只截断保存内容。
    max_input_bytes: int = 16384
    flush_interval: float = 0.1  # 进度保存间隔，秒。
    poll_interval: float = 0.5  # 队列及运行状态检查间隔，秒。
    auth_interval: float = 5  # 当前授权复核间隔，秒。

    def __post_init__(self) -> None:
        validate_positive(self)


def load_runtime_config(values: dict[str, str | None]) -> RuntimeConfig:
    return RuntimeConfig(**positive_values(RuntimeConfig, values))
