"""Minimal GitHub identity verification; no upstream credentials are persisted."""

import base64
import hashlib
import json
import re
import secrets
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.auth.config import GitHubOAuthConfig
from app.errors import InvalidInputError, ServiceUnavailableError
from app.values import utc_now

OAUTH_COOKIE = "app_github_oauth"
OAUTH_COOKIE_PATH = "/api/auth/github"
OAUTH_TTL = 600
RETURN_PATH = re.compile(
    r"/(?:|agents(?:/(?:new|[a-zA-Z0-9-]+))?|skills(?:/(?:new|[a-zA-Z0-9-]+))?|"
    r"knowledge|design-system|brains|rules|conversations(?:/(?:new|[a-zA-Z0-9-]+))?|"
    r"avatars/svg|avatars/playground(?:/[a-z0-9-]+)?|avatars/rive/programmer)"
)


def safe_return_path(value: str) -> str:
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return "/"
    if len(value.encode()) > 2048:
        return "/"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "/"
    if parsed.netloc or parsed.scheme or not RETURN_PATH.fullmatch(parsed.path):
        return "/"
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


class GitHubOAuth:
    def __init__(
        self,
        config: GitHubOAuthConfig,
        clock: Callable[[], datetime] = utc_now,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config, self.clock, self.transport = config, clock, transport
        key = hashlib.sha256(b"niuma-github-oauth-v1:" + config.client_secret.encode()).digest()
        self.cipher = Fernet(base64.urlsafe_b64encode(key))

    def start(self, next_path: str) -> tuple[str, str]:
        if not self.config.enabled:
            raise ServiceUnavailableError("github_unavailable", "GitHub 登录尚未配置。")
        context = {
            "state": secrets.token_urlsafe(32),
            "verifier": secrets.token_urlsafe(32),
            "next": safe_return_path(next_path),
        }
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(context["verifier"].encode()).digest())
            .decode()
            .rstrip("=")
        )
        url = "https://github.com/login/oauth/authorize?" + urlencode(
            {
                "client_id": self.config.client_id,
                "redirect_uri": self.config.callback_url,
                "scope": "",
                "state": context["state"],
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        cookie = self.cipher.encrypt_at_time(
            json.dumps(context, ensure_ascii=False).encode(), int(self.clock().timestamp())
        ).decode()
        return url, cookie

    def context(self, cookie: str | None, state: str | None) -> dict[str, str]:
        if not self.config.enabled:
            raise ServiceUnavailableError("github_unavailable", "GitHub 登录尚未配置。")
        try:
            if not cookie or len(cookie) > 4096 or not state or len(state) > 128:
                raise ValueError
            context = json.loads(
                self.cipher.decrypt_at_time(
                    cookie.encode(), OAUTH_TTL, int(self.clock().timestamp())
                )
            )
            if (
                not isinstance(context, dict)
                or any(
                    not isinstance(context.get(key), str) for key in ("state", "verifier", "next")
                )
                or not secrets.compare_digest(context["state"], state)
            ):
                raise ValueError
            context["next"] = safe_return_path(context["next"])
            return context
        except (InvalidToken, ValueError, TypeError, UnicodeError):
            raise InvalidInputError("github_expired", "登录请求已失效，请重新发起。") from None

    @staticmethod
    def _json(client: httpx.Client, method: str, url: str, **kwargs) -> dict:
        # Bound both token and profile responses; never reflect upstream bodies or exceptions.
        with client.stream(method, url, **kwargs) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 65536:
                    raise ValueError
            value = json.loads(content)
            if not isinstance(value, dict):
                raise ValueError
            return value

    def identity(self, code: str, verifier: str) -> tuple[str, str]:
        if not code or len(code) > 512:
            raise InvalidInputError("github_failed", "GitHub 登录资料不完整，请重新发起。")
        try:
            with httpx.Client(
                timeout=10, follow_redirects=False, trust_env=False, transport=self.transport
            ) as client:
                token = self._json(
                    client,
                    "POST",
                    "https://github.com/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": self.config.client_id,
                        "client_secret": self.config.client_secret,
                        "redirect_uri": self.config.callback_url,
                        "code": code,
                        "code_verifier": verifier,
                    },
                ).get("access_token")
                if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", token):
                    raise ValueError
                profile = self._json(
                    client,
                    "GET",
                    "https://api.github.com/user",
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {token}",
                        "User-Agent": "NiumaCrew",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
            subject, username = profile.get("id"), profile.get("login")
            if (
                type(subject) is not int
                or subject <= 0
                or not isinstance(username, str)
                or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username)
            ):
                raise ValueError
            return str(subject), username
        except (httpx.HTTPError, ValueError, UnicodeError):
            raise ServiceUnavailableError(
                "github_failed", "暂时无法完成 GitHub 登录，请重试。"
            ) from None
