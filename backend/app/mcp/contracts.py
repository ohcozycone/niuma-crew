import hashlib
from dataclasses import dataclass, field


def exposed_name(connection_id: str, name: str) -> str:
    # 加入连接身份，避免不同服务的同名工具冲突。
    return (
        "mcp_"
        + connection_id.replace("-", "")
        + "_"
        + hashlib.sha256(name.encode()).hexdigest()[:16]
    )


@dataclass(frozen=True, slots=True)
class McpOutcome:
    content: str
    status: str = "succeeded"
    data: dict = field(default_factory=dict)
    sources: tuple[dict, ...] = ()
    error_code: str | None = None
