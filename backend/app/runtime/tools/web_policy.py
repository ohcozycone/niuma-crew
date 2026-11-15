"""Conservative public URL policy; this is not control of a provider's redirect engine."""

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import unquote, urlsplit, urlunsplit


class WebFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def public_url(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise WebFailure("web_url_denied")
    if any(ord(char) < 33 or ord(char) == 127 for char in value) or "\\" in value:
        raise WebFailure("web_url_denied")
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        raise WebFailure("web_url_denied") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 80 if parsed.scheme == "http" else 443}
        or parsed.query
        or parsed.fragment
        or "." not in host
        or host.endswith(
            (".localhost", ".local", ".internal", ".lan", ".home", ".test", ".invalid")
        )
        or re.search(
            r"(?i)(?:token|secret|password|api[-_]?key|auth|signature|invite|reset)[=/]",
            unquote(parsed.path),
        )
        or re.search(r"(?i)/[a-z0-9_-]{48,}(?:/|$)", unquote(parsed.path))
    ):
        raise WebFailure("web_url_denied")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            raise WebFailure("web_url_denied") from None
        if not re.fullmatch(r"[a-z0-9.-]+", host):
            raise WebFailure("web_url_denied")
    else:
        if not address.is_global:
            raise WebFailure("web_url_denied")
    return urlunsplit((parsed.scheme, host, parsed.path or "/", "", ""))


async def resolve_public(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return list({info[4][0] for info in infos})


async def checked_url(
    value: str, resolve: Callable[[str], Awaitable[list[str]]] = resolve_public
) -> str:
    value = public_url(value)
    try:
        addresses = await resolve(urlsplit(value).hostname or "")
        if not addresses or any(not ipaddress.ip_address(item).is_global for item in addresses):
            raise WebFailure("web_url_denied")
    except (OSError, ValueError):
        raise WebFailure("web_url_denied") from None
    return value


def query_urls(value: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9+.-]*://\S+", value, flags=re.IGNORECASE)


def public_query(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise WebFailure("tool_arguments_invalid")
    if re.search(
        r"(?i)(?:bearer\s+|sk-[a-z0-9]|(?:api[_-]?key|password|token|secret)\s*[=:])", value
    ):
        raise WebFailure("web_query_denied")
    for match in query_urls(value):
        public_url(match)
    return value.strip()
