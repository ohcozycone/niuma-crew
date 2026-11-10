import re
from datetime import timedelta

import pytest
from run_helpers import empty_conversation
from test_capability_runtime import ScriptedModel, execute, response
from test_conversations import send
from test_employee_knowledge import assemble
from test_employee_knowledge_runtime import MARKER, KnowledgeModel, actions, configure

from app.auth.actor import Actor
from app.conversations.context import accepted_run_id
from app.execution.evidence_models import RunKnowledgeEvidence
from app.execution.models import Run
from app.knowledge.models import LibraryChunk
from app.values import utc_now


def initial(client, monkeypatch):
    agent, conversation, base, document, settings = configure(client)
    accepted = send(client, conversation, "住宿标准是什么？").json()["response"]
    result = execute(client, monkeypatch, KnowledgeModel(read_source=False), accepted)
    assert result["status"] == "succeeded", result
    citation = re.search(r"\[K-[^\]]+\]\([^)]+\)", result["content"]).group()
    return agent, conversation, base, document, settings, accepted, citation


def remove_document(client, first, base, document):
    with client.app.state.database.transaction() as db:
        owner = db.get(Run, first["id"]).owner_user_id
    actor = Actor("user", "", owner, "admin", "admin", utc_now() + timedelta(hours=1))
    client.app.state.knowledge_documents.remove(actor, base["id"], document["id"])


def test_repeated_followups_reuse_current_evidence_without_new_search(api_client, monkeypatch):
    _, conversation, _, _, _, previous, citation = initial(api_client, monkeypatch)
    for question in ("刚才的标准再说明一下", "给我一个简短版本"):
        accepted = send(api_client, conversation, question).json()["response"]
        model = ScriptedModel(responses=[response("住宿每晚最高400元。" + citation)])
        result = execute(api_client, monkeypatch, model, accepted)
        assert result["status"] == "succeeded", result
        assert citation in result["content"]
        assert len(model.prompts) == 1
        assert MARKER in model.prompts[0]
        assert "本轮已重新核验的历史知识证据" in model.prompts[0]
        steps = actions(api_client, accepted["id"])
        assert [item["kind"] for item in steps] == ["knowledge", "model_call"]
        assert steps[0]["safe_details"]["operation"] == "history_reuse"
        assert steps[0]["safe_details"]["sources"]
        with api_client.app.state.database.transaction() as db:
            row = db.get(Run, accepted["id"])
            refs = row.config_snapshot["knowledge"]["history_evidence"]
            assert refs[0]["source_run_id"] == previous["id"]
            assert db.get(RunKnowledgeEvidence, (row.id, refs[0]["evidence_id"]))
        previous = accepted


def test_revalidated_history_can_be_read_through_the_current_run_tool(api_client, monkeypatch):
    _, conversation, _, _, _, _, citation = initial(api_client, monkeypatch)
    identifier = re.search(r"K-[a-f0-9]{16}", citation).group()
    accepted = send(api_client, conversation, "补读刚才的原文").json()["response"]
    model = ScriptedModel(
        responses=[
            response(
                "补读资料。",
                [
                    {
                        "id": "followup-read",
                        "name": "read_knowledge_source",
                        "args": {"evidence_id": identifier},
                    }
                ],
            ),
            response("按原文仍为400元。" + citation),
        ]
    )
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert [item["safe_details"].get("tool") for item in actions(api_client, accepted["id"])] == [
        None,
        None,
        "read_knowledge_source",
        None,
    ]


def test_another_conversation_cannot_import_a_citation_from_the_question(api_client, monkeypatch):
    agent, _, _, _, _, _, citation = initial(api_client, monkeypatch)
    conversation = empty_conversation(api_client, agent["id"])
    accepted = send(api_client, conversation, "请沿用这个来源" + citation).json()["response"]
    result = execute(
        api_client, monkeypatch, ScriptedModel(responses=[response(citation)]), accepted
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "knowledge_citation_invalid"


@pytest.mark.parametrize("mutation", ["delete", "rechunk", "unmount", "budget"])
def test_stale_or_omitted_history_loses_citation_authority_in_model_input(
    api_client, monkeypatch, mutation
):
    agent, conversation, base, document, settings, first, citation = initial(
        api_client, monkeypatch
    )
    if mutation == "delete":
        remove_document(api_client, first, base, document)
    elif mutation == "rechunk":
        with api_client.app.state.database.transaction() as db:
            identifier = re.search(r"K-[a-f0-9]{16}", citation).group()
            chunk_id = db.get(RunKnowledgeEvidence, (first["id"], identifier)).chunk_id
            chunk = db.get(LibraryChunk, chunk_id)
            chunk.snapshot = {**chunk.snapshot, "text": "重处理后的其他规则"}
    elif mutation == "unmount":
        assert assemble(api_client, agent["id"], []).status_code == 200
    else:
        monkeypatch.setattr(
            api_client.app.state.knowledge_evidence, "capture_history", lambda *_, **__: []
        )
    accepted = send(api_client, conversation, "刚才的标准还能适用吗？").json()["response"]
    model = ScriptedModel(responses=[response("当前依据不足，需要重新检索确认。")])
    result = execute(api_client, monkeypatch, model, accepted)
    assert result["status"] == "succeeded", result
    assert not re.search(r"K-[a-f0-9]{16}", model.prompts[0])
    assert "请重新检索" in model.prompts[0]
    with api_client.app.state.database.transaction() as db:
        # 只清理本轮送模副本，已保存的成功历史不变。
        from app.conversations.models import Message

        assert citation in db.get(Message, first["id"]).body
        assert (
            not db.get(Run, accepted["id"])
            .config_snapshot.get("knowledge", {})
            .get("history_evidence")
        )


def test_capture_is_bounded_and_rejects_wrong_origin_identity_or_link(api_client, monkeypatch):
    _, _, _, _, _, first, citation = initial(api_client, monkeypatch)
    service = api_client.app.state
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, first["id"])
        captured = row.config_snapshot["knowledge"]
        scope = {"owner_user_id": row.owner_user_id, "thread_id": row.thread_id}
        capture = service.knowledge_evidence.capture_history
        assert capture(db, captured, [(row.id, citation)], 0, **scope) == []
        for invalid in (citation[:-1] + "#fake)", citation.replace("/sources/", "/fake/")):
            assert capture(db, captured, [(row.id, invalid)], 18000, **scope) == []
        wrong = {**captured, "agent_id": "00000000-0000-0000-0000-000000000000"}
        assert capture(db, wrong, [(row.id, citation)], 18000, **scope) == []
        for key in ("owner_user_id", "thread_id"):
            wrong_scope = {**scope, key: "000000000000"}
            assert capture(db, captured, [(row.id, citation)], 18000, **wrong_scope) == []
        row.status = "failed"
        assert capture(db, captured, [(row.id, citation)], 18000, **scope) == []


def test_context_source_lookup_only_accepts_selected_replies_in_this_conversation(
    api_client, monkeypatch
):
    agent, conversation, _, _, _, first, _ = initial(api_client, monkeypatch)
    another = empty_conversation(api_client, agent["id"])
    with api_client.app.state.database.transaction() as db:
        assert accepted_run_id(db, another["id"]) is None
        assert accepted_run_id(db, conversation["id"]) == first["id"]


def test_deletion_after_acceptance_invalidates_inherited_evidence(api_client, monkeypatch):
    _, conversation, base, document, _, first, citation = initial(api_client, monkeypatch)
    accepted = send(api_client, conversation, "继续解释").json()["response"]
    remove_document(api_client, first, base, document)
    result = execute(
        api_client, monkeypatch, ScriptedModel(responses=[response(citation)]), accepted
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "knowledge_source_changed"


@pytest.mark.parametrize("delete_source", [False, True])
def test_finished_checkpoint_rechecks_history_without_a_second_model_call(
    api_client, monkeypatch, delete_source
):
    from app.conversations.models import Message

    _, conversation, base, document, _, first, citation = initial(api_client, monkeypatch)
    accepted = send(api_client, conversation, "继续说明").json()["response"]
    # 在存档提交与业务发布之间停止，不覆盖已交付回复或重放接纳副作用。
    coordinator = api_client.app.state.runs
    with monkeypatch.context() as pending:
        pending.setattr(coordinator, "complete", lambda _: None)
        assert (
            execute(
                api_client, monkeypatch, ScriptedModel(responses=[response(citation)]), accepted
            )["status"]
            == "running"
        )
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, accepted["id"])
        assert row.checkpoint_id
        assert db.get(Message, accepted["id"]).body is None
        row.status, row.started_at = "queued", None
    if delete_source:
        remove_document(api_client, first, base, document)
    model = ScriptedModel(responses=[])
    result = execute(api_client, monkeypatch, model, accepted)
    assert not model.prompts
    assert result["status"] == ("failed" if delete_source else "succeeded"), result
    if delete_source:
        assert result["error"]["code"] == "knowledge_source_changed"
        assert not result["content"]
    else:
        assert result["content"] == citation
        assert [step["kind"] for step in actions(api_client, accepted["id"])] == [
            "knowledge",
            "model_call",
        ]
