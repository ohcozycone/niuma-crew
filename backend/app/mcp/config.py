from dataclasses import dataclass
from urllib.parse import urlsplit

from app.auth.config import AuthConfig, normalize_origin

OAUTH_CALLBACK_PATH = "/api/tool-connections/oauth/callback"


def oauth_callback_origin(value: str) -> str:
    try:
        callback = urlsplit(value)
        origin = normalize_origin(f"{callback.scheme}://{callback.netloc}")
        if (
            callback.username is not None
            or callback.password is not None
            or callback.query
            or callback.fragment
            or callback.path != OAUTH_CALLBACK_PATH
            or (
                callback.scheme != "https"
                and callback.hostname not in {"localhost", "127.0.0.1", "::1"}
            )
        ):
            raise ValueError
    except ValueError:
        raise ValueError(
            "TOOL_OAUTH_CALLBACK_URL 必须为本站 HTTPS 回调地址，本机允许 HTTP。"
        ) from None
    return origin


@dataclass(frozen=True)
class ToolConfig:
    timeout_seconds: int = 30
    max_response_bytes: int = 2 * 1024 * 1024
    max_catalog_bytes: int = 1024 * 1024
    stdio_enabled: bool = False
    max_stdio_processes: int = 4
    stdio_wait_seconds: float = 10
    oauth_callback_url: str | None = None
    oauth_session_seconds: int = 600
    oauth_max_sessions: int = 8

    def __post_init__(self):
        if self.max_stdio_processes < 1 or self.stdio_wait_seconds <= 0:
            raise ValueError("MCP stdio 进程数与等待时限必须大于零。")
        if self.oauth_callback_url is not None:
            oauth_callback_origin(self.oauth_callback_url)
        if self.oauth_session_seconds <= 0 or self.oauth_max_sessions < 1:
            raise ValueError("OAuth 等待时限与会话数必须大于零。")

    def validate(self, auth: AuthConfig) -> None:
        if (
            self.oauth_callback_url is not None
            and oauth_callback_origin(self.oauth_callback_url) not in auth.allowed_origins
        ):
            raise ValueError("TOOL_OAUTH_CALLBACK_URL 必须属于 AUTH_ALLOWED_ORIGINS。")
