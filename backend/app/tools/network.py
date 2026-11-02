"""Pin approved DNS answers and bound streamed MCP responses before parsing."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

from app.errors import InvalidInputError, ServiceUnavailableError
from app.tools.config import ToolConfig


def validate_endpoint(value: str, config: ToolConfig) -> tuple[str, int]:
    try:
        url = urlsplit(value)
        port = url.port or (443 if url.scheme == "https" else 80)
    except ValueError:
        raise InvalidInputError("tool_endpoint_invalid", "工具地址格式无效。") from None
    host = (url.hostname or "").lower()
    if (
        url.scheme not in ("https", "http")
        or not host
        or url.username
        or url.password
        or url.query
        or url.fragment
        or host not in (*config.allowed_hosts, *config.private_hosts)
        or (url.scheme != "https" and host not in config.private_hosts)
    ):
        raise InvalidInputError(
            "tool_endpoint_denied",
            "工具地址必须属于部署者允许的主机，且不能包含凭证、查询参数或片段。",
        )
    return host, port


class BoundedStream(httpx.AsyncByteStream):
    def __init__(self, stream, limit: int):
        self.stream, self.limit = stream, limit

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > self.limit:
                raise InvalidInputError("tool_result_too_large", "工具响应超过接收上限。")
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class PinnedTransport(httpx.AsyncBaseTransport):
    def __init__(self, endpoint: str, config: ToolConfig):
        self.host, self.port = validate_endpoint(endpoint, config)
        self.scheme = urlsplit(endpoint).scheme
        self.config = config
        self.inner = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        if (
            request.url.host.lower() != self.host
            or port != self.port
            or request.url.scheme != self.scheme
        ):
            raise InvalidInputError("tool_endpoint_denied", "工具请求改变了获准目标。")
        try:
            answers = await asyncio.get_running_loop().getaddrinfo(
                self.host, self.port, type=socket.SOCK_STREAM
            )
        except OSError:
            raise ServiceUnavailableError(
                "tool_dns_failed", "无法解析工具服务域名，请检查后端的 DNS 或网络配置。"
            ) from None
        addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
        if not addresses:
            raise InvalidInputError("tool_endpoint_denied", "工具目标无法解析。")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            # Private destinations require an exact deployer allowlist. Metadata,
            # multicast and unspecified addresses are never valid MCP endpoints.
            if (
                ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
                or (not ip.is_global and self.host not in self.config.private_hosts)
            ):
                raise InvalidInputError(
                    "tool_endpoint_denied",
                    "工具域名解析到未获准的私网或保留地址，请检查后端 DNS 或代理配置。",
                )
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=addresses[0]),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": self.host},
        )
        response = await self.inner.handle_async_request(pinned)
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            await response.aclose()
            raise InvalidInputError(
                "tool_result_too_large", "工具响应使用未支持的压缩编码，未进行无界解压。"
            )
        response.stream = BoundedStream(response.stream, self.config.max_response_bytes)
        return response

    async def aclose(self):
        await self.inner.aclose()
