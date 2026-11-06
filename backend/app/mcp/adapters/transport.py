"""Bridge the SDK's HTTP client to the platform's bounded HTTP transport."""

from urllib.parse import urlsplit

import httpx
import httpx2

from app.errors import InvalidInputError
from app.mcp.network import PinnedTransport


class ResponseStream(httpx2.AsyncByteStream):
    def __init__(self, response: httpx.Response):
        self.response = response

    async def __aiter__(self):
        if self.response.is_stream_consumed:
            yield self.response.content
        else:
            async for chunk in self.response.aiter_raw():
                yield chunk

    async def aclose(self):
        await self.response.aclose()


class SDKTransport(httpx2.AsyncBaseTransport):
    """Preserve one network implementation while adapting public SDK HTTP types."""

    def __init__(
        self, endpoint, config, *, transport_factory=None, oauth=False, observer=None, failures=None
    ):
        self.endpoint, self.config = endpoint, config
        self.transport_factory, self.oauth = transport_factory, oauth
        self.observer = observer
        self.failures = failures if failures is not None else []
        self.transports = {}

    async def handle_async_request(self, request):
        target = str(request.url)
        resource = urlsplit(self.endpoint)
        parsed = urlsplit(target)
        same_origin = (parsed.scheme, parsed.netloc) == (resource.scheme, resource.netloc)
        if not self.oauth and not same_origin:
            raise InvalidInputError("tool_endpoint_denied", "工具请求改变了配置目标。")
        if (
            self.oauth
            and not same_origin
            and request.headers.get("authorization", "").startswith("Bearer ")
        ):
            raise InvalidInputError("tool_endpoint_denied", "不能向其他授权目标转发 MCP Token。")
        if (
            self.oauth
            and parsed.scheme != "https"
            and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        ):
            raise InvalidInputError(
                "oauth_incompatible", "OAuth 授权端点需要 HTTPS，本机回调除外。"
            )
        # OAuth endpoints can carry protocol query parameters; credentials stay in
        # the body/headers. Each underlying transport still pins its exact origin.
        endpoint = target.split("?", 1)[0]
        key = endpoint if self.oauth else self.endpoint
        if key not in self.transports:
            self.transports[key] = (
                self.transport_factory()
                if self.transport_factory
                else PinnedTransport(key, self.config)
            )
        try:
            response = await self.transports[key].handle_async_request(
                httpx.Request(
                    request.method,
                    target,
                    headers=list(request.headers.multi_items()),
                    content=await request.aread(),
                    extensions=request.extensions,
                )
            )
        except Exception as error:
            from app.errors import ServiceError

            if isinstance(error, ServiceError):
                self.failures.append(error)
            raise
        if (
            self.observer
            and request.method == "GET"
            and response.is_success
            and "application/json" in response.headers.get("content-type", "")
        ):
            await response.aread()
            await self.observer(target, response.json())
        return httpx2.Response(
            response.status_code,
            headers=list(response.headers.multi_items()),
            stream=ResponseStream(response),
            extensions=response.extensions,
        )

    async def aclose(self):
        for transport in self.transports.values():
            await transport.aclose()
