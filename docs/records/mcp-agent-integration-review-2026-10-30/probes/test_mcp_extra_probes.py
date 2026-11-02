"""Offline review probes; no real services, app databases, credentials or subprocesses."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from app.errors import InvalidInputError, PermissionDeniedError
from app.tools.adapters.mcp import MCPClient, descriptor
from app.tools.config import ToolConfig
from app.tools.policy import authorize_arguments


def test_approved_generic_mcp_four_url_schema_is_rejected_by_page_heuristic():
    binding = {
        "kind": "mcp_http",
        "tool_name": "batch_compare_urls",
        "scope_policy": {"mode": "provider"},
        "input_schema": {
            "type": "object",
            "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
            "required": ["urls"],
        },
    }
    with pytest.raises(InvalidInputError) as caught:
        authorize_arguments(binding, {"urls": [f"https://example.com/{i}" for i in range(4)]})
    assert caught.value.code == "tool_arguments_invalid"
    assert caught.value.message == "每次最多读取三个网页。"


def test_approved_generic_uri_schema_is_rejected_as_webpage():
    binding = {
        "kind": "mcp_http",
        "tool_name": "open_resource",
        "scope_policy": {"mode": "provider"},
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    }
    with pytest.raises(PermissionDeniedError) as caught:
        authorize_arguments(binding, {"url": "resource://catalog/library"})
    assert caught.value.code == "tool_url_denied"


def test_only_server_version_change_changes_descriptor_hash():
    raw = {"name": "query_docs", "description": "Query docs", "inputSchema": {"type": "object"}}

    def value(version):
        tool = SimpleNamespace(
            name="query_docs",
            description="Query docs",
            args_schema={"type": "object"},
            metadata={"mcp": {"server": {"name": "docs", "version": version}}},
        )
        return descriptor(tool, raw)

    first, second = value("1.0.0"), value("1.0.1")
    assert first["raw_descriptor"] == second["raw_descriptor"]
    assert first["name"] == second["name"]
    assert first["description"] == second["description"]
    assert first["input_schema"] == second["input_schema"]
    assert first["descriptor_hash"] != second["descriptor_hash"]


def test_real_protocol_is_error_preserves_failed_status():
    server = FastMCP("mcp-review-iserror")

    @server.tool
    async def query_docs(query: str) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text="No indexed library matches this query")],
            isError=True,
        )

    app = server.http_app(path="/mcp", stateless_http=True)
    client = MCPClient(
        "https://fixture.test/mcp",
        {},
        ToolConfig(),
        transport_factory=lambda: httpx.ASGITransport(app=app),
    )

    async def scenario():
        async with app.router.lifespan_context(app):
            catalog = await client.discover()
            guards = []

            async def guard():
                guards.append(True)

            content, artifact, status = await client.invoke(
                "query_docs", {"query": "a missing library"}, catalog[0]["descriptor_hash"], guard
            )
            assert status == "error"
            assert "No indexed library" in str(content)
            assert guards == [True]

    asyncio.run(scenario())


def test_real_protocol_server_version_only_change_rejects_unchanged_tool():
    servers = [FastMCP("mcp-review-version", version=v) for v in ("1.0.0", "1.0.1")]

    async def query_docs(query: str) -> str:
        return "Found docs for " + query

    for server in servers:
        server.tool(query_docs)
    apps = [s.http_app(path="/mcp", stateless_http=True) for s in servers]
    clients = [
        MCPClient(
            "https://fixture.test/mcp",
            {},
            ToolConfig(),
            transport_factory=lambda app=app: httpx.ASGITransport(app=app),
        )
        for app in apps
    ]

    async def scenario():
        async with (
            apps[0].router.lifespan_context(apps[0]),
            apps[1].router.lifespan_context(apps[1]),
        ):
            first, second = (await clients[0].discover())[0], (await clients[1].discover())[0]
            assert first["raw_descriptor"] == second["raw_descriptor"]
            assert first["input_schema"] == second["input_schema"]
            assert first["description"] == second["description"]
            assert first["metadata"]["mcp"]["server"]["version"] == "1.0.0"
            assert second["metadata"]["mcp"]["server"]["version"] == "1.0.1"
            guards = []

            async def guard():
                guards.append(True)

            with pytest.raises(InvalidInputError) as caught:
                await clients[1].invoke(
                    "query_docs", {"query": "hello"}, first["descriptor_hash"], guard
                )
            assert caught.value.code == "tool_catalog_changed"
            assert caught.value.catalog[0]["raw_descriptor"] == first["raw_descriptor"]
            assert guards == []

    asyncio.run(scenario())
