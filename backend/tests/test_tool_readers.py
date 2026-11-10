from test_agent_foundations import SearchClient, search_grant, send
from test_capability_runtime import ScriptedModel, execute, response, setup
from test_tool_discovery import discovery_response

from app.resources.mcp.contracts import exposed_name


def search_setup(client, *, skills=False):
    _, _, agent, conversation = setup(client)
    if not skills:
        saved = client.patch(
            f"/api/agents/{agent['id']}",
            json={"expected_revision": agent["revision"], "skill_assignments": []},
        )
        assert saved.status_code == 200, saved.text
        agent = saved.json()
    SearchClient.calls, SearchClient.before_guard = 0, None
    connection = search_grant(client, agent)
    return agent, conversation, connection


def test_mcp_and_base_file_tools_preserve_downloadable_sources(api_client, monkeypatch):
    _, conversation, connection = search_setup(api_client)
    name = exposed_name(connection["id"], "tavily_search")
    accepted = send(api_client, conversation)
    model = ScriptedModel(
        responses=[
            discovery_response(),
            response("", [{"name": name, "id": "search", "args": {"query": "网页"}}]),
            response("已根据工具返回内容生成摘要。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert model.bindings and all(
        {"read_tool_result", "read_file", "write_file"} <= set(tools)
        and (name in tools or "search_tools" in tools)
        for tools in model.bindings
    )
    assert "/sources/large_tool_results/search" in model.prompts[-1]
    source = next(
        ref
        for ref in api_client.app.state.files.sources(accepted["id"])
        if ref["name"].startswith("tool-result-")
    )
    assert (
        api_client.get(f"/api/conversations/{conversation['id']}/files/{source['id']}").status_code
        == 200
    )


def test_source_reader_rejects_unknown_source_without_reporting_a_skill_failure(
    api_client, monkeypatch
):
    _, conversation, connection = search_setup(api_client, skills=True)
    accepted = send(api_client, conversation)
    model = ScriptedModel(
        responses=[
            discovery_response(),
            response(
                "",
                [
                    {
                        "name": exposed_name(connection["id"], "tavily_search"),
                        "id": "search",
                        "args": {"query": "网页"},
                    }
                ],
            ),
            response(
                "",
                [
                    {
                        "name": "read_file",
                        "id": "source",
                        "args": {"file_path": "/sources/unknown/page.txt"},
                    }
                ],
            ),
            response("没有找到该来源文件。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert "not found" in model.prompts[-1].lower()
    assert all("read_file" in tools for tools in model.bindings)
    assert "/sources/large_tool_results/search" in model.prompts[-1]


def test_base_source_reader_reads_mcp_results_without_any_workspace_assignment(
    api_client, monkeypatch
):
    agent, conversation, connection = search_setup(api_client)
    accepted = send(api_client, conversation)
    id = accepted["id"]

    class SourceReader(ScriptedModel):
        def _generate(self, *args, **kwargs):
            if self._index == 2:
                source = next(
                    value
                    for value in api_client.app.state.files.sources(id)
                    if value["name"].startswith("tool-result-")
                )
                self.responses[2] = response(
                    "",
                    [
                        {
                            "name": "read_file",
                            "id": "read-source",
                            "args": {"file_path": f"/sources/{source['id']}/{source['name']}"},
                        }
                    ],
                )
            return super()._generate(*args, **kwargs)

    model = SourceReader(
        responses=[
            discovery_response(),
            response(
                "",
                [
                    {
                        "name": exposed_name(connection["id"], "tavily_search"),
                        "id": "search",
                        "args": {"query": "网页"},
                    }
                ],
            ),
            response(),
            response("已分段读取来源正文。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert "/sources/large_tool_results/search" in model.prompts[2]
    assert [step["kind"] for step in result["steps"]] == [
        "model_call",
        "tool_call",
        "model_call",
        "tool_call",
        "model_call",
        "tool_call",
        "model_call",
    ]
