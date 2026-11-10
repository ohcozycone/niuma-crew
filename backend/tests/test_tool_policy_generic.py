import asyncio
import json
from types import SimpleNamespace

import pytest

from app.common.errors import InvalidInputError
from app.resources.mcp.policy import authorize_arguments, validate_scope
from app.runtime.contracts.tools import ToolInvocation
from app.runtime.execution.errors import ExecutionFailure
from app.runtime.execution.tool_results import ToolResults


def test_url_named_parameters_are_generic():
    binding = {
        "kind": "mcp_http",
        "tool_name": "tavily_search",
        "input_schema": {"type": "object"},
        "scope_policy": {"mode": "provider", "arguments": {"max_results": {"maximum": 20}}},
    }
    arguments = {
        "urls": ["record:1", "record:2", "record:3", "record:4"],
        "max_results": 12,
        "include_answer": True,
    }
    authorize_arguments(binding, arguments)
    assert arguments["max_results"] == 12 and arguments["include_answer"]
    with pytest.raises(InvalidInputError):
        authorize_arguments(binding, {"max_results": 21})


@pytest.mark.parametrize(
    "field,value",
    [
        ("summary_keep_tokens", 999999),
        ("memory_scope", None),
        ("memory_reset", "false"),
    ],
)
def test_current_snapshot_rejects_invalid_engine_inputs_before_preparation(
    api_client, field, value
):
    from test_capability_runtime import setup, submit

    from app.runtime.execution.snapshot_rules import validate_snapshot

    _, _, _, conversation = setup(api_client)
    accepted = submit(api_client, conversation).json()["response"]
    row, _ = api_client.app.state.run_worker.store.load(accepted["id"])
    snapshot = {**row.config_snapshot, field: value}
    with pytest.raises(ExecutionFailure, match="checkpoint_unavailable"):
        validate_snapshot(snapshot)


def test_unmapped_domain_scope_is_rejected_at_save_and_execution():
    scope = {"mode": "provider", "allowed_domains": ["example.com"]}
    with pytest.raises(InvalidInputError):
        validate_scope(scope, "mcp_http")
    with pytest.raises(InvalidInputError):
        authorize_arguments({"kind": "mcp_http", "scope_policy": scope, "input_schema": {}}, {})


def test_official_file_tools_define_real_parameter_schemas():
    from app.runtime.tools.workspace import workspace_tools

    tools = workspace_tools(
        {"mode": "virtual", "read_roots": ["/workspace"], "write_roots": ["/workspace"]}
    )
    write = next(tool for tool in tools if tool["tool_name"] == "write_file")
    assert set(write["input_schema"]["required"]) == {"file_path", "content"}
    assert all(tool["kind"] == "workspace" for tool in tools)
    assert "execute" not in {tool["tool_name"] for tool in tools}


def test_new_result_paging_uses_frozen_text_and_preserves_opaque_artifact():
    saved = {}

    def save(name, body):
        saved["body"] = body
        return {"id": "result", "name": name}

    resources = SimpleNamespace(
        save_source=save,
        read_file=lambda _: saved["body"],
        list_sources=lambda: [{"id": "result", "name": "tool-result-x.json"}],
    )
    results = ToolResults({"tools": [{"binding_id": "binding", "kind": "mcp_http"}]}, resources)
    data = {
        "content": [{"type": "text", "text": "正文" * 10000}],
        "structured": {"unknown_shape": {"raw_content": "opaque"}},
    }
    asyncio.run(results.preserve(ToolInvocation("tool:x", "binding", "fetch", {}), data, "failed"))
    stored = json.loads(saved["body"])
    assert stored["data"] == data and stored["platform_result"]["format_version"] == 2
    fragments = []
    cursor = 0
    while cursor is not None:
        page = json.loads(results.read_page("result", cursor, 6000))
        fragments.append(page["text"])
        cursor = page["next_offset"]
    assert "".join(fragments) == stored["text"]
