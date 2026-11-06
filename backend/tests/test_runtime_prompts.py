"""Capability guidance must describe only the frozen tools and scopes."""

import json

import pytest

from app.execution.prompts import server_instructions, tool_instructions


def test_knowledge_only_does_not_advertise_mcp_file_or_execution_capabilities():
    assert tool_instructions({}) == ""
    prompt = tool_instructions({"tools": [{"kind": "knowledge"}]})
    assert prompt
    assert "read_tool_result" not in prompt
    assert "文件操作范围" not in prompt
    assert "execute" not in prompt
    assert "/outputs" not in prompt


def test_file_guidance_keeps_each_operations_actual_scope():
    tools = [
        {
            "kind": "native",
            "tool_name": "read_file",
            "scope_policy": {"read_roots": ["/inputs"], "write_roots": []},
        },
        {
            "kind": "native",
            "tool_name": "write_file",
            "scope_policy": {"read_roots": [], "write_roots": ["/outputs"]},
        },
    ]
    prompt = tool_instructions({"tools": tools})
    scopes = json.loads(next(line for line in prompt.splitlines() if line.startswith("[")))
    by_name = {scope.pop("operation"): scope for scope in scopes}
    assert by_name == {tool["tool_name"]: tool["scope_policy"] for tool in tools}
    assert "/sources" not in prompt and "/workspace" not in prompt
    assert "read_tool_result" not in prompt and "execute" not in prompt


def test_execute_only_is_described_as_sandbox_instead_of_file_root_permission():
    prompt = tool_instructions(
        {"tools": [{"kind": "native", "tool_name": "execute", "scope_policy": {}}]}
    )
    assert "execute" in prompt and "沙箱" in prompt
    assert "文件操作范围" not in prompt
    assert "read_tool_result" not in prompt


def test_mcp_guidance_preserves_pending_state_and_deduplicates_connected_services():
    connected = {
        "kind": "mcp_http",
        "connection_id": "connected",
        "tool_name": "search",
        "exposed_name": "mcp_search",
        "server_instructions": "CONNECTED_GUIDANCE",
    }
    pending = {
        **connected,
        "connection_id": "pending",
        "auth_required": True,
        "exposed_name": "pending_search",
        "server_instructions": "PENDING_GUIDANCE",
    }
    snapshot = {"tools": [connected, connected, pending]}
    prompt = tool_instructions(snapshot)
    operations = json.loads(next(line for line in prompt.splitlines() if line.startswith("[")))
    assert {item["call_name"]: item["auth_required"] for item in operations} == {
        "mcp_search": False,
        "pending_search": True,
    }
    assert "read_tool_result" in prompt and "文件操作范围" not in prompt
    guidance = server_instructions(snapshot)
    assert guidance.count("CONNECTED_GUIDANCE") == 1
    assert "PENDING_GUIDANCE" not in guidance
    assert server_instructions({"tools": [pending]}) == ""


@pytest.mark.parametrize("skill_mode", ["none", "available", "selected"])
def test_real_model_call_keeps_base_guidance_and_conditional_skill_loading(
    api_client, monkeypatch, skill_mode
):
    from configuration_helpers import patch_current
    from test_capability_runtime import ScriptedModel, execute, response, setup, submit

    skill, _, agent, conversation = setup(api_client)
    if skill_mode == "none":
        changed = patch_current(
            api_client,
            f"/api/agents/{agent['id']}",
            json={"skill_assignments": []},
        )
        assert changed.status_code == 200, changed.text
    selected = [skill["id"]] if skill_mode == "selected" else None
    accepted = submit(api_client, conversation, selected=selected)
    assert accepted.status_code == 202, accepted.text
    model = ScriptedModel(responses=[response("已完成")])
    result = execute(api_client, monkeypatch, model, accepted.json()["response"])
    assert result["status"] == "succeeded", result
    assert len(model.prompts) == 1
    prompt = model.prompts[0]
    assert "你是 NiumaCrew 的数字员工" in prompt and '"审阅员"' in prompt
    assert ("可用技能目录（按需使用，不相关时直接回答）" in prompt) == (skill_mode != "none")
    assert ("BODY_MARKER_P1" in prompt) == (skill_mode == "selected")
    assert all(
        placeholder not in prompt
        for placeholder in ("{skills_locations}", "{skills_load_warnings}", "{skills_list}")
    )
