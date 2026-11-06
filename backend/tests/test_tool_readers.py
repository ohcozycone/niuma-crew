"""Only advertise executable file tools; Skill reads do not grant source-file access."""

from test_agent_foundations import SearchClient, search_grant, send
from test_capability_runtime import ScriptedModel, execute, response, setup

from app.mcp.contracts import exposed_name


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


def test_mcp_only_advertises_no_skill_reader_and_preserves_downloadable_sources(
    api_client, monkeypatch
):
    _, conversation, connection = search_setup(api_client)
    name = exposed_name(connection["id"], "tavily_search")
    accepted = send(api_client, conversation)
    model = ScriptedModel(
        responses=[
            response("", [{"name": name, "id": "search", "args": {"query": "网页"}}]),
            response("已根据工具返回内容生成摘要。"),
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert model.bindings and all(tools == [name, "read_tool_result"] for tools in model.bindings)
    assert '"source_files_readable": false' in model.prompts[-1]
    assert '"raw_result"' not in model.prompts[-1]
    sources = next(
        step["safe_details"]["sources"] for step in result["steps"] if step["kind"] == "tool_call"
    )
    assert sources and all(source["path"] not in model.prompts[-1] for source in sources)
    assert (
        api_client.get(
            f"/api/conversations/{conversation['id']}/files/{sources[0]['file_id']}"
        ).status_code
        == 200
    )


def test_skill_reader_does_not_grant_source_access_or_report_a_skill_failure(
    api_client, monkeypatch
):
    _, conversation, connection = search_setup(api_client, skills=True)
    accepted = send(api_client, conversation)
    model = ScriptedModel(
        responses=[
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
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "failed", result
    assert result["error"]["code"] == "tool_not_allowed"
    assert all("read_file" in tools for tools in model.bindings)
    assert '"raw_result"' not in model.prompts[-1]


def test_explicit_source_reader_can_read_mcp_results_without_activating_a_skill(
    api_client, monkeypatch
):
    agent, conversation, connection = search_setup(api_client)
    native = api_client.post(
        "/api/tool-connections",
        json={
            "name": "只读来源",
            "kind": "native",
            "provider_key": "workspace",
            "public_config": {},
        },
    )
    assert native.status_code == 201, native.text
    current = api_client.get(f"/api/agents/{agent['id']}").json()
    saved = api_client.patch(
        f"/api/agents/{agent['id']}",
        json={
            "expected_revision": current["revision"],
            "tool_grants": [
                {
                    "connection_id": connection["id"],
                    "tools": ["tavily_search"],
                    "expected_descriptors": {
                        "tavily_search": SearchClient.catalog[0]["descriptor_hash"]
                    },
                    "scope_policy": {"mode": "provider", "max_calls": 5},
                },
                {
                    "connection_id": native.json()["id"],
                    "tools": ["read_file"],
                    "scope_policy": {
                        "mode": "workspace",
                        "max_calls": 5,
                        "read_roots": ["/sources"],
                        "write_roots": [],
                    },
                },
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    accepted = send(api_client, conversation)
    id = accepted["id"]

    class SourceReader(ScriptedModel):
        def _generate(self, *args, **kwargs):
            if self._index == 1:
                source = next(
                    value
                    for value in api_client.app.state.files.sources(id)
                    if value["name"] == "page-1.txt"
                )
                self.responses[1] = response(
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
    assert '"source_files_readable": true' in model.prompts[1]
    assert '"raw_result"' in model.prompts[1]
    assert [step["kind"] for step in result["steps"]] == [
        "model_call",
        "tool_call",
        "model_call",
        "tool_call",
        "model_call",
    ]
