"""MCP resource limits and trusted process settings."""

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ToolConfig:
    timeout_seconds: int = 30
    max_response_bytes: int = 2 * 1024 * 1024
    max_catalog_bytes: int = 1024 * 1024
    max_model_bytes: int = 24 * 1024
    stdio_enabled: bool = False
    max_stdio_processes: int = 4
    stdio_wait_seconds: float = 10
    oauth_callback_url: str = "http://localhost:3000/api/tool-connections/oauth/callback"
    oauth_session_seconds: int = 600
    oauth_max_sessions: int = 8

    def __post_init__(self):
        if self.max_stdio_processes < 1 or self.stdio_wait_seconds <= 0:
            raise ValueError("MCP stdio 进程数与等待时限必须大于零。")
        callback = urlsplit(self.oauth_callback_url)
        if (
            not callback.hostname
            or callback.username is not None
            or callback.password is not None
            or callback.query
            or callback.fragment
            or callback.path != "/api/tool-connections/oauth/callback"
            or (
                callback.scheme != "https"
                and not (
                    callback.scheme == "http"
                    and callback.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
        ):
            raise ValueError("TOOL_OAUTH_CALLBACK_URL 必须为本站 HTTPS 回调地址，本机允许 HTTP。")
        if self.oauth_session_seconds <= 0 or self.oauth_max_sessions < 1:
            raise ValueError("OAuth 等待时限与会话数必须大于零。")
