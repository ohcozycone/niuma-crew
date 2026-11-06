"""Thread memory and per-run references exercised through the real Agent and SQLite."""

from checkpoint_helpers import checkpoint_values
from configuration_helpers import patch_current
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from run_helpers import checkpoint_store
from test_capability_runtime import ScriptedModel, execute, response, setup, submit
from test_employee_knowledge_runtime import KnowledgeModel, configure

from app.execution.models import Run


def saved_state(client, run_id):
    with client.app.state.database.transaction() as db:
        row = db.get(Run, run_id)
        return checkpoint_values(
            checkpoint_store(client), row.id, row.checkpoint_id, thread_id=row.thread_id
        )


def test_second_turn_keeps_official_tool_messages_and_resets_only_run_usage(
    api_client, monkeypatch
):
    skill, _, _, conversation = setup(api_client)
    first = submit(api_client, conversation, content="REMEMBER_FIRST").json()["response"]
    tool_call = {
        "name": "read_file",
        "id": "load-first",
        "args": {"file_path": f"/skills/s-{skill['id']}/SKILL.md"},
    }
    done = execute(
        api_client,
        monkeypatch,
        ScriptedModel(responses=[response("", [tool_call]), response("FIRST_ANSWER")]),
        first,
    )
    assert done["status"] == "succeeded", done
    second = submit(api_client, conversation, content="SECOND_QUESTION").json()["response"]
    model = ScriptedModel(responses=[response("SECOND_ANSWER")])
    finished = execute(api_client, monkeypatch, model, second)
    assert finished["status"] == "succeeded", finished
    state = saved_state(api_client, second["id"])
    assert any(
        isinstance(m, ToolMessage) and m.tool_call_id == "load-first" for m in state["messages"]
    )
    assert any(isinstance(m, AIMessage) and m.tool_calls for m in state["messages"])
    assert (
        sum(
            isinstance(m, HumanMessage) and m.content == "SECOND_QUESTION"
            for m in state["messages"]
        )
        == 1
    )
    assert state["model_usage"]["total_tokens"] == 15
    assert "REMEMBER_FIRST" in model.prompts[0]


def test_reference_message_reaches_model_without_rewriting_persistent_user_input(
    api_client, monkeypatch
):
    _, conversation, *_ = configure(api_client, mode="always")
    run = submit(api_client, conversation, content="住宿标准是什么？").json()["response"]
    model = KnowledgeModel(mode="always")
    done = execute(api_client, monkeypatch, model, run)
    assert done["status"] == "succeeded", done
    assert "本轮平台知识预检索结果" in model.prompts[0]
    messages = saved_state(api_client, run["id"])["messages"]
    human = [m for m in messages if isinstance(m, HumanMessage)]
    assert any(m.content == "住宿标准是什么？" for m in human)
    assert all("本轮平台知识预检索结果" not in str(m.content) for m in human)


def test_added_skill_is_discovered_next_turn_without_losing_ordinary_memory(
    api_client, monkeypatch
):
    skill, _, agent, conversation = setup(api_client)
    first = submit(api_client, conversation, content="MY_MARKER_137").json()["response"]
    assert (
        execute(api_client, monkeypatch, ScriptedModel(responses=[response("记住了")]), first)[
            "status"
        ]
        == "succeeded"
    )
    added = api_client.post(
        "/api/skills",
        json={"name": "NEW_SKILL_MARKER", "description": "新技能", "instructions": "技能正文"},
    ).json()
    saved = patch_current(
        api_client,
        f"/api/agents/{agent['id']}",
        json={"skill_assignments": [{"skill_id": skill["id"]}, {"skill_id": added["id"]}]},
    )
    assert saved.status_code == 200, saved.text
    second = submit(api_client, conversation, content="继续").json()["response"]
    model = ScriptedModel(responses=[response("新技能可用")])
    done = execute(api_client, monkeypatch, model, second)
    assert done["status"] == "succeeded", done
    assert "MY_MARKER_137" in model.prompts[0] and "NEW_SKILL_MARKER" in model.prompts[0]


def test_added_mcp_is_registered_and_callable_next_turn_with_memory(api_client, monkeypatch):
    from test_agent_foundations import SearchClient, search_grant

    from app.mcp.contracts import exposed_name

    _, _, agent, conversation = setup(api_client)
    first = submit(api_client, conversation, content="FIRST_MCP_MARKER").json()["response"]
    assert (
        execute(api_client, monkeypatch, ScriptedModel(responses=[response("已记住")]), first)[
            "status"
        ]
        == "succeeded"
    )
    SearchClient.calls, SearchClient.before_guard = 0, None
    connection = search_grant(api_client, agent)
    name = exposed_name(connection["id"], "tavily_search")
    second = submit(api_client, conversation, content="现在用新增工具搜索").json()["response"]
    model = ScriptedModel(
        responses=[
            response("", [{"name": name, "id": "new-search", "args": {"query": "test"}}]),
            response("完成"),
        ]
    )
    done = execute(api_client, monkeypatch, model, second)
    assert done["status"] == "succeeded", done
    assert "FIRST_MCP_MARKER" in model.prompts[0]
    assert name in model.bindings[0] and SearchClient.calls == 1


def test_removed_skill_invalidates_old_skill_text_and_ordinary_memory(api_client, monkeypatch):
    skill, _, agent, conversation = setup(api_client)
    first = submit(
        api_client, conversation, selected=[skill["id"]], content="OLD_PRIVATE_MARKER"
    ).json()["response"]
    assert (
        execute(api_client, monkeypatch, ScriptedModel(responses=[response("已记住")]), first)[
            "status"
        ]
        == "succeeded"
    )
    assert (
        patch_current(
            api_client, f"/api/agents/{agent['id']}", json={"skill_assignments": []}
        ).status_code
        == 200
    )
    second = submit(api_client, conversation, content="继续").json()["response"]
    model = ScriptedModel(responses=[response("重新开始")])
    done = execute(api_client, monkeypatch, model, second)
    assert done["status"] == "succeeded", done
    assert "OLD_PRIVATE_MARKER" not in model.prompts[0]
    assert "BODY_MARKER_P1" not in model.prompts[0]
    assert "请重新检索" in model.prompts[0]
    assert all(
        "请重新检索" not in str(m.content)
        for m in saved_state(api_client, second["id"])["messages"]
    )


def test_old_output_is_not_republished_when_next_turn_keeps_messages(api_client, monkeypatch):
    from test_agent_foundations import workspace

    _, _, agent, conversation = setup(api_client)
    workspace(api_client, agent)
    first = submit(api_client, conversation).json()["response"]
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": "write_file",
                        "id": "write",
                        "args": {"file_path": "/outputs/first.txt", "content": "first"},
                    }
                ],
            ),
            response("已生成"),
        ]
    )
    done = execute(api_client, monkeypatch, model, first)
    assert done["status"] == "succeeded" and len(done["files"]) == 1
    second = submit(api_client, conversation).json()["response"]
    result = execute(
        api_client, monkeypatch, ScriptedModel(responses=[response("本轮没有新输出")]), second
    )
    assert result["status"] == "succeeded" and result["files"] == []
    assert not any(
        path.startswith("/outputs")
        for path in saved_state(api_client, second["id"]).get("files", {})
    )


def test_revoking_inherited_mcp_blocks_memory_before_next_model(api_client, monkeypatch):
    from test_agent_foundations import SearchClient, search_grant

    from app.mcp.contracts import exposed_name

    skill, _, agent, conversation = setup(api_client)
    SearchClient.calls, SearchClient.before_guard = 0, None
    connection = search_grant(api_client, agent)
    name = exposed_name(connection["id"], "tavily_search")
    first = submit(api_client, conversation).json()["response"]
    model = ScriptedModel(
        responses=[
            response("", [{"name": name, "id": "first-search", "args": {"query": "test"}}]),
            response("已检索"),
        ]
    )
    assert execute(api_client, monkeypatch, model, first)["status"] == "succeeded"
    second = submit(api_client, conversation).json()["response"]

    class Revoke(ScriptedModel):
        def _generate(self, *args, **kwargs):
            if self._index == 0:
                assert (
                    patch_current(
                        api_client, f"/api/agents/{agent['id']}", json={"tool_grants": []}
                    ).status_code
                    == 200
                )
            return super()._generate(*args, **kwargs)

    model = Revoke(
        responses=[
            response(
                "",
                [
                    {
                        "name": "read_file",
                        "id": "next",
                        "args": {"file_path": f"/skills/s-{skill['id']}/SKILL.md"},
                    }
                ],
            ),
            response("不应生成"),
        ]
    )
    result = execute(api_client, monkeypatch, model, second)
    assert result["status"] == "failed", result
    assert len(model.prompts) == 1 and SearchClient.calls == 1
