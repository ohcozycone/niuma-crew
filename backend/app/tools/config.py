"""MCP endpoint policy is set by the deployer, not by tool output."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolConfig:
    allowed_hosts: tuple[str, ...] = ("mcp.tavily.com",)
    private_hosts: tuple[str, ...] = ()
    timeout_seconds: int = 30
    max_response_bytes: int = 2 * 1024 * 1024
    max_catalog_bytes: int = 256 * 1024
    max_model_bytes: int = 24 * 1024
    stdio_enabled: bool = False
    max_stdio_processes: int = 4
    stdio_wait_seconds: float = 10

    def __post_init__(self):
        if self.max_stdio_processes < 1 or self.stdio_wait_seconds <= 0:
            raise ValueError("MCP stdio 进程数与等待时限必须大于零。")
