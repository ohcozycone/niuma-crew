"""Plain tool contracts shared with the runtime and execution host."""

import hashlib
from dataclasses import dataclass, field


def exposed_name(connection_id: str, name: str) -> str:
    # Stable and bounded even when two servers export the same tool name.
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
