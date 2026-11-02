"""认证配置：受信任浏览器来源、会话期限及可选 GitHub 登录。"""

from dataclasses import dataclass, field
from urllib.parse import urlsplit


def normalize_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("AUTH_ALLOWED_ORIGINS 必须为无路径的 HTTP/HTTPS 来源。")
    port = parsed.port
    hostname = parsed.hostname.lower()
    host = f"[{hostname}]" if ":" in hostname else hostname
    suffix = f":{port}" if port and port != (443 if parsed.scheme == "https" else 80) else ""
    return f"{parsed.scheme}://{host}{suffix}"


@dataclass(frozen=True)
class AuthConfig:
    """写请求的来源与 Cookie 约束；所有会话期限的单位均为秒。"""

    # 完整来源（协议、主机和端口），不包含路径；写请求必须精确匹配。
    allowed_origins: tuple[str, ...] = ("http://127.0.0.1:3000", "http://localhost:3000")
    cookie_secure: bool = False  # HTTPS 部署必须开启，非本机来源不允许关闭。
    max_age_seconds: int = 604800  # 用户会话的绝对期限，最长一年。
    idle_timeout_seconds: int = 86400  # 用户会话的闲置期限，不得超过绝对期限。
    guest_max_age_seconds: int = 604800  # 游客会话的绝对期限，最长一年。

    def __post_init__(self) -> None:
        if not self.allowed_origins:
            raise ValueError("AUTH_ALLOWED_ORIGINS 不能为空。")
        origins = tuple(normalize_origin(origin) for origin in self.allowed_origins)
        object.__setattr__(self, "allowed_origins", origins)
        if not 1 <= self.idle_timeout_seconds <= self.max_age_seconds <= 31536000:
            raise ValueError("AUTH_SESSION 有效期必须为正数、闲置期不超过绝对期限，最长一年。")
        if not 1 <= self.guest_max_age_seconds <= 31536000:
            raise ValueError("AUTH_GUEST_MAX_AGE_SECONDS 必须为 1 到 31536000。")
        for origin in origins:
            parsed = urlsplit(origin)
            if self.cookie_secure and parsed.scheme != "https":
                raise ValueError("Secure Cookie 要求 AUTH_ALLOWED_ORIGINS 全部使用 HTTPS。")
            if not self.cookie_secure and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("非本机来源必须开启 AUTH_COOKIE_SECURE。")


def load_auth_config(values: dict[str, str | None]) -> AuthConfig:
    secure = values.get("AUTH_COOKIE_SECURE", "false")
    if secure not in {"true", "false"}:
        raise ValueError("AUTH_COOKIE_SECURE 必须为 true 或 false。")
    raw_origins = (
        values.get("AUTH_ALLOWED_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000") or ""
    )
    origins = tuple(part.strip() for part in raw_origins.split(","))
    try:
        max_age = int(values.get("AUTH_SESSION_MAX_AGE_SECONDS", "604800"))
        idle = int(values.get("AUTH_SESSION_IDLE_TIMEOUT_SECONDS", "86400"))
        guest_age = int(values.get("AUTH_GUEST_MAX_AGE_SECONDS", "604800"))
    except (ValueError, TypeError) as error:
        raise ValueError("AUTH_SESSION/AUTH_GUEST 有效期必须为整数。") from error
    return AuthConfig(origins, secure == "true", max_age, idle, guest_age)


@dataclass(frozen=True)
class GitHubOAuthConfig:
    """三项全部缺省时关闭登录入口，启用时必须全部配置。"""

    client_id: str = ""
    client_secret: str = field(default="", repr=False)  # 仅供后端使用，不参与 repr。
    callback_url: str = ""  # 必须为受信任来源下的 /api/auth/github/callback。

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret and self.callback_url)

    def validate(self, auth: AuthConfig) -> None:
        if not any((self.client_id, self.client_secret, self.callback_url)):
            return
        if not self.enabled:
            raise ValueError("GitHub 登录需同时配置 Client ID、Client Secret 和 Callback URL。")
        try:
            callback = urlsplit(self.callback_url)
            origin = normalize_origin(f"{callback.scheme}://{callback.netloc}")
        except ValueError:
            raise ValueError("GITHUB_OAUTH_CALLBACK_URL 不是有效的回调地址。") from None
        if (
            origin not in auth.allowed_origins
            or callback.path != "/api/auth/github/callback"
            or callback.query
            or callback.fragment
        ):
            raise ValueError("GitHub 回调必须为受信任来源下的 /api/auth/github/callback。")


def load_github_oauth_config(values: dict[str, str | None], auth: AuthConfig) -> GitHubOAuthConfig:
    config = GitHubOAuthConfig(
        client_id=(values.get("GITHUB_OAUTH_CLIENT_ID") or "").strip(),
        client_secret=(values.get("GITHUB_OAUTH_CLIENT_SECRET") or "").strip(),
        callback_url=(values.get("GITHUB_OAUTH_CALLBACK_URL") or "").strip(),
    )
    config.validate(auth)
    return config
