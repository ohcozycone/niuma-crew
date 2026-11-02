"""Registry metadata is inert input, never a vendor-specific executable adapter."""

import json
from dataclasses import replace


def descriptor():
    return {
        "name": "io.github.example/docs",
        "title": "Docs",
        "description": "Documentation lookup",
        "packages": [
            {
                "registryType": "npm",
                "identifier": "@example/docs-mcp",
                "version": "1.2.3",
                "transport": {"type": "stdio"},
                "environmentVariables": [
                    {
                        "name": "DOCS_API_KEY",
                        "description": "Optional account key",
                        "isRequired": False,
                        "isSecret": True,
                    }
                ],
            }
        ],
        "remotes": [
            {
                "type": "streamable-http",
                "url": "https://mcp.tavily.com/mcp",
                "headers": [{"name": "Authorization", "isRequired": False, "isSecret": True}],
            }
        ],
    }


def preview(client, body):
    return client.post("/api/mcp-config/preview", json={"configuration": json.dumps(body)})


def test_registry_offers_http_and_stdio_without_installing_or_creating_resources(api_client):
    api_client.app.state.tool_connections.config = replace(
        api_client.app.state.tool_connections.config, stdio_enabled=True
    )
    api_client.app.state.mcp_definitions.config = api_client.app.state.tool_connections.config
    result = preview(api_client, descriptor())
    assert result.status_code == 200, result.text
    entries = result.json()["entries"]
    assert [entry["transport"] for entry in entries] == ["http", "stdio"]
    assert entries[0]["auth_type"] == "bearer"
    assert entries[1]["args"] == ["-y", "@example/docs-mcp@1.2.3"]
    assert entries[1]["input_fields"][0] == {
        "name": "DOCS_API_KEY",
        "description": "Optional account key",
        "is_required": False,
        "is_secret": True,
    }
    assert api_client.get("/api/mcp-services").json() == []
    assert api_client.get("/api/tool-connections").json() == []
    created = api_client.post(
        "/api/mcp-services",
        json={
            key: entries[0][key]
            for key in ("name", "description", "transport", "url", "input_fields")
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["input_fields"][0]["name"] == "Authorization"


def test_unsupported_registry_inputs_are_not_silently_dropped(api_client):
    data = descriptor()
    data["remotes"][0]["headers"][0]["variables"] = {"token": {"isSecret": True}}
    assert preview(api_client, data).status_code == 422
    data = descriptor()
    data["remotes"].append({"type": "sse", "url": "https://example.com/sse"})
    response = preview(api_client, data)
    assert response.status_code == 200
    assert response.json()["warnings"]


def test_client_type_and_secret_placeholders_can_be_imported_without_echoing_keys(api_client):
    response = preview(
        api_client,
        {
            "mcpServers": {
                "docs": {
                    "type": "http",
                    "url": "https://mcp.tavily.com/mcp",
                    "headers": {"Authorization": "Bearer ${DOCS_KEY}"},
                }
            }
        },
    )
    assert response.status_code == 200, response.text
    assert "${DOCS_KEY}" not in response.text
    assert response.json()["entries"][0]["auth_type"] == "bearer"


def test_registry_input_fields_cannot_inject_runtime_environment(api_client):
    api_client.app.state.tool_connections.config = replace(
        api_client.app.state.tool_connections.config, stdio_enabled=True
    )
    api_client.app.state.mcp_definitions.config = api_client.app.state.tool_connections.config
    data = descriptor()
    data["packages"][0]["environmentVariables"][0]["name"] = "NODE_OPTIONS"
    assert preview(api_client, data).status_code == 422
