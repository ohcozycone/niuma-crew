"""集中定义运行预算、调度与观察参数，由 AppConfig 装配。"""

from dataclasses import dataclass, fields
from math import isfinite


@dataclass(frozen=True)
class RuntimeConfig:
    """除 enabled 外，字段均可用 RUN_ 加字段大写名覆盖；修改后需重启。"""

    enabled: bool = True  # 测试可注入 False 以关闭 Runner；没有对应环境变量。

    # 并发数控制执行，队列与账号容量控制准入。
    concurrency: int = 2  # 同时执行的 Run 数。
    queue_capacity: int = 20  # 等待执行的 Run 数上限。
    per_user_capacity: int = 2  # 单个账号未结束的 Run 数上限，包含排队与执行。
    queue_timeout: float = 30  # 排队时限，秒。
    run_timeout: float = 180  # 单次执行总时限，秒。

    # 接受 Run 时冻结进快照，执行中修改配置不会改变已接受的预算。
    recursion_limit: int = 64  # LangGraph 计算步数上限，不等于模型调用或工具调用次数。
    max_model_calls: int = 8  # 普通 Agent 每 Run 的模型调用次数上限。
    max_skill_reads: int = 16  # 每 Run 的技能加载次数上限，预加载与实际读取共用。
    max_tool_calls: int = 32  # 包含实际技能读取，预加载仍只占技能预算。
    max_output_tokens: int = 4096  # 每次模型调用的输出 token 上限。
    max_output_bytes: int = 131072  # 每轮及最终回答的 UTF-8 字节上限，超限停止执行。
    max_reasoning_bytes: int = 32768  # 每 Run 保存思考文字的 UTF-8 字节上限，只截断展示。
    context_bytes: int = 131072  # 模型输入上下文的序列化字节上限，不等于 token 数。

    max_input_bytes: int = 16384  # 单条用户输入的 UTF-8 字节上限。
    context_pairs: int = 20  # 最多纳入上下文的历史成功对话轮次。

    # 进度、授权与 SSE 观察参数，间隔和期限的单位均为秒。
    flush_interval: float = 0.1  # 执行中草稿与思考的保存间隔。
    poll_interval: float = 0.25  # 运行状态检查及 SSE 快照轮询间隔。
    auth_interval: float = 5  # 执行中重新检查身份、配置及资源许可的间隔。
    subscription_limit: int = 4  # 单账号并发 SSE 订阅数上限。
    subscription_seconds: float = 300  # 单条 SSE 连接的最长存活时间。

    def __post_init__(self) -> None:
        for field in fields(self):
            if field.name == "enabled":
                continue
            value = getattr(self, field.name)
            if field.type is int:
                if type(value) is not int or value <= 0:
                    raise ValueError(f"RUN_{field.name.upper()} 必须为正整数。")
            elif (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"RUN_{field.name.upper()} 必须为有限正数。")


def load_runtime_config(values: dict[str, str | None]) -> RuntimeConfig:
    """解析已合并的配置来源；显式空值或格式错误必须报错，不回退默认值。"""
    kwargs = {}
    for field in fields(RuntimeConfig):
        if field.name == "enabled":
            continue
        key = "RUN_" + field.name.upper()
        if key in values:
            parser = int if field.type is int else float
            try:
                kwargs[field.name] = parser(values[key])
            except (ValueError, TypeError):
                raise ValueError(f"{key} 格式错误。") from None
    return RuntimeConfig(**kwargs)
