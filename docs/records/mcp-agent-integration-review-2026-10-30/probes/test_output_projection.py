"""Offline evidence for public draft/terminal projections and history provenance."""

import json
import os
import tempfile
from pathlib import Path

from test_capability_runtime import ScriptedModel, execute, response, setup, submit

import app.agent_runtime.langchain as runtime
from app.conversations.models import ConversationRun
from app.conversations.queries import read_response
from app.execution.models import Run

OUTPUT = Path(
    os.environ.get(
        "NIUMA_MCP_AUDIT_OUTPUT",
        str(Path(tempfile.gettempdir()) / "niuma-mcp-review-20261030-recheck"),
    )
)
OUTPUT.mkdir(parents=True, exist_ok=True)


def test_evidence_failure_projection(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    accepted = submit(
        api_client, conversation, content="读取 https://example.com/docs 页面内容"
    ).json()
    observed = {}
    original = runtime.verify_web_reads

    def intercept(*args):
        with api_client.app.state.database.transaction() as db:
            observed["before_verification"] = read_response(
                db, db.get(Run, accepted["id"])
            ).model_dump(mode="json")
        return original(*args)

    monkeypatch.setattr(runtime, "verify_web_reads", intercept)
    result = execute(
        api_client,
        monkeypatch,
        ScriptedModel(responses=[response("我已经读取网页，网页介绍虚构的新功能。")]),
        accepted,
    )
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, accepted["id"])
        observed["after_failure"] = read_response(db, row).model_dump(mode="json")
        reply_id = db.get(ConversationRun, row.id).reply_message_id
    observed["terminal_sse"] = api_client.get(
        f"/api/conversations/{conversation['id']}/responses/{reply_id}/events"
    ).text
    next_run = submit(api_client, conversation, content="继续").json()
    with api_client.app.state.database.transaction() as db:
        observed["following_run_input"] = db.get(Run, next_run["id"]).input_snapshot
    assert observed["before_verification"]["status"] == "running"
    assert observed["before_verification"]["content_state"] == "draft"
    assert observed["before_verification"]["content"].startswith("我已经读取网页")
    assert result["status"] == "failed"
    assert observed["after_failure"]["content"] == ""
    assert observed["after_failure"]["content_state"] == "empty"
    assert observed["after_failure"]["steps"][0]["output_text"].startswith("我已经读取网页")
    assert len(observed["following_run_input"]) == 1
    (OUTPUT / "output-projection.json").write_text(
        json.dumps(observed, ensure_ascii=False, indent=2)
    )


def test_succeeded_claim_enters_next_history_without_provenance(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    accepted = submit(
        api_client, conversation, content="查看 LangChain 最新文档有哪些新功能"
    ).json()
    result = execute(
        api_client,
        monkeypatch,
        ScriptedModel(responses=[response("我已经查过官方文档并逐条核实，新功能是虚构功能甲。")]),
        accepted,
    )
    assert result["status"] == "succeeded"
    next_run = submit(api_client, conversation, content="展开说明功能甲").json()
    with api_client.app.state.database.transaction() as db:
        messages = db.get(Run, next_run["id"]).input_snapshot
    assert [message["role"] for message in messages] == ["user", "assistant", "user"]
    assert "逐条核实" in messages[1]["content"]
    assert set(messages[1]) == {"id", "role", "content"}
    (OUTPUT / "history-provenance.json").write_text(
        json.dumps(messages, ensure_ascii=False, indent=2)
    )
