"""MCP onboarding accepts new hosts and local HTTP without deployment lists."""

import asyncio
import json

import httpx
import pytest

from app.errors import InvalidInputError
from app.mcp.config import ToolConfig
from app.mcp.network import PinnedTransport


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://mcp.notion.com/mcp",
        "https://new-mcp.example/mcp",
        "http://127.0.0.1:8765/mcp",
        "http://localhost:8765/mcp",
        "http://192.168.1.10:8765/mcp",
        "http://[::1]:8765/mcp",
    ],
)
def test_import_service_and_account_accept_unlisted_hosts(api_client, endpoint):
    preview = api_client.post(
        "/api/mcp-config/preview",
        json={"configuration": json.dumps({"mcpServers": {"test": {"url": endpoint}}})},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["entries"][0]["url"] == endpoint
    service = api_client.post("/api/mcp-services", json={"name": "New MCP", "url": endpoint})
    assert service.status_code == 201, service.text
    connection = api_client.post(
        "/api/tool-connections",
        json={
            "name": "My MCP",
            "service_id": service.json()["id"],
            "kind": "mcp_http",
            "public_config": {"url": endpoint},
        },
    )
    assert connection.status_code == 201, connection.text


@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///tmp/mcp",
        "https://user:secret@new-mcp.example/mcp",
        "https://new-mcp.example/mcp?token=secret",
        "https://new-mcp.example/mcp#fragment",
    ],
)
def test_service_still_rejects_invalid_endpoint_structure(api_client, endpoint):
    response = api_client.post("/api/mcp-services", json={"name": "Invalid MCP", "url": endpoint})
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "tool_endpoint_denied"


def test_local_http_transport_pins_address_and_rejects_target_change(monkeypatch):
    async def scenario():
        async def resolve(*args, **kwargs):
            return [(2, 1, 6, "", ("127.0.0.1", 8765))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        endpoint = "http://localhost:8765/mcp"
        transport = PinnedTransport(endpoint, ToolConfig())
        calls = []

        def upstream(request):
            calls.append(request)
            assert request.url.host == "127.0.0.1"
            assert request.url.port == 8765
            assert request.headers["host"] == "localhost:8765"
            return httpx.Response(200, content=b"local MCP")

        transport.inner = httpx.MockTransport(upstream)
        async with httpx.AsyncClient(transport=transport) as client:
            assert (await client.get(endpoint)).status_code == 200
            for changed in (
                "http://other.example:8765/mcp",
                "http://localhost:8766/mcp",
                "https://localhost:8765/mcp",
            ):
                with pytest.raises(InvalidInputError, match="工具请求改变了"):
                    await client.get(changed)
        assert len(calls) == 1

    asyncio.run(scenario())
