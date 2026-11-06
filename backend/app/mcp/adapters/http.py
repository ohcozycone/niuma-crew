"""Official LangChain MCP adapter with explicit connection and network limits."""

import json
from contextlib import asynccontextmanager

import httpx
import httpx2
from fastmcp.client.transports import StreamableHttpTransport
from langchain.mcp import MCPAdapter, as_langchain_tool
from langchain_core.messages import ToolMessage

from app.errors import InvalidInputError, ServiceError
from app.mcp.adapters.transport import SDKTransport
from app.values import digest


def descriptor(tool, raw=None) -> dict:
    value = {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.args_schema
        if isinstance(tool.args_schema, dict)
        else tool.args_schema.model_json_schema(),
        "metadata": tool.metadata or {},
        "raw_descriptor": raw,
    }
    return {**value, "descriptor_hash": digest(value), "recovery": "never"}


class MCPClient:
    def __init__(
        self,
        endpoint: str,
        headers: dict,
        config,
        *,
        transport_factory=None,
        auth=None,
        observer=None,
        access=None,
    ):
        self.endpoint, self.headers, self.config = endpoint, headers, config
        self.transport_factory = transport_factory
        self.auth, self.observer, self.access = auth, observer, access
        self.instructions = ""
        self.expected_instructions_hash = None

    def capture_instructions(self, adapter):
        instructions = adapter.client.instructions or ""
        if not isinstance(instructions, str) or len(instructions.encode()) > 16384:
            raise InvalidInputError("tool_instructions_too_large", "MCP 服务说明超过上限。")
        self.instructions = instructions

    @asynccontextmanager
    async def session(self):
        if self.access is not None:
            async with self.access() as headers:
                async with self._session(headers) as adapter:
                    yield adapter
        else:
            async with self._session(self.headers) as adapter:
                yield adapter

    @asynccontextmanager
    async def _session(self, request_headers):
        rejection = None
        failures: list[ServiceError] = []

        async def record_auth(response):
            nonlocal rejection
            rejection = response.status_code if response.status_code in (401, 403) else None

        def factory(**kwargs):
            kwargs.pop("follow_redirects", None)
            kwargs.pop("timeout", None)
            headers = httpx2.Headers(kwargs.pop("headers", {}))
            headers["Accept-Encoding"] = "identity"
            # No environment proxy or transparent SDK retries may change identity/target.
            return httpx2.AsyncClient(
                **kwargs,
                event_hooks={"response": [record_auth]},
                headers=headers,
                transport=SDKTransport(
                    self.endpoint,
                    self.config,
                    transport_factory=self.transport_factory,
                    oauth=self.auth is not None,
                    observer=self.observer,
                    failures=failures,
                ),
                trust_env=False,
                follow_redirects=False,
                timeout=httpx2.Timeout(self.config.timeout_seconds),
            )

        transport = StreamableHttpTransport(
            self.endpoint,
            headers=request_headers,
            auth=self.auth,
            httpx_client_factory=factory,
            max_sse_event_size=self.config.max_response_bytes,
        )
        try:
            async with MCPAdapter(transport) as adapter:
                yield adapter
        except Exception as error:
            if isinstance(error, ServiceError):
                raise
            if failures:
                raise failures[-1] from None
            status = auth_status(error) or rejection
            if status == 401:
                raise InvalidInputError(
                    "tool_auth_required", "MCP 拒绝了当前 Token，请在账号连接中检查或更换 Token。"
                ) from None
            if status == 403:
                raise InvalidInputError(
                    "tool_permission_denied", "MCP 账号无权执行此操作，请检查上游权限和操作范围。"
                ) from None
            raise

    async def _tools(self, adapter):
        remote = await adapter.client.list_tools(cache_mode="bypass")
        tools = [
            (
                await as_langchain_tool(item, adapter.client),
                item.model_dump(mode="json", by_alias=True, exclude_none=True),
            )
            for item in remote
        ]
        values = [descriptor(tool, raw) for tool, raw in tools]
        if len(values) > 128:
            raise InvalidInputError(
                "tool_catalog_too_large", f"服务返回了 {len(values)} 个工具，超过 128 个上限。"
            )
        size = len(json.dumps(values, ensure_ascii=False).encode())
        if size > self.config.max_catalog_bytes:
            raise InvalidInputError(
                "tool_catalog_too_large",
                f"工具目录约 {size / 1024:.0f} KiB，超过 {self.config.max_catalog_bytes / 1024:.0f} KiB 上限。",
            )
        if len({item["name"] for item in values}) != len(values):
            raise InvalidInputError(
                "tool_catalog_invalid", "服务返回了重复的工具名称，无法保存目录。"
            )
        return [(tool, value) for (tool, _), value in zip(tools, values, strict=True)]

    async def discover(self) -> list[dict]:
        async with self.session() as adapter:
            self.capture_instructions(adapter)
            return [value for _, value in await self._tools(adapter)]

    async def invoke(self, name: str, arguments: dict, expected_hash: str, guard):
        async with self.session() as adapter:
            self.capture_instructions(adapter)
            tools = await self._tools(adapter)
            selected = next(((tool, value) for tool, value in tools if tool.name == name), None)
            tool, current = selected if selected else (None, None)
            if (
                current is None
                or current["descriptor_hash"] != expected_hash
                or (
                    self.expected_instructions_hash is not None
                    and digest(self.instructions) != self.expected_instructions_hash
                )
            ):
                error = InvalidInputError(
                    "tool_catalog_changed", "远端工具目录已改变，请管理员重新审核。"
                )
                error.catalog = [value for _, value in tools]
                error.instructions = self.instructions
                raise error
            await guard()
            value = await tool.ainvoke(
                {"name": name, "args": arguments, "id": "upstream", "type": "tool_call"}
            )
            if isinstance(value, ToolMessage):
                return value.content, value.artifact, value.status
            return value, None, "success"


def auth_status(error, seen=None):
    seen = set() if seen is None else seen
    if id(error) in seen:
        return None
    seen.add(id(error))
    if isinstance(
        error, (httpx.HTTPStatusError, httpx2.HTTPStatusError)
    ) and error.response.status_code in (401, 403):
        return error.response.status_code
    for child in [*getattr(error, "exceptions", ()), error.__cause__, error.__context__]:
        if child is not None and (status := auth_status(child, seen)):
            return status
    return None
