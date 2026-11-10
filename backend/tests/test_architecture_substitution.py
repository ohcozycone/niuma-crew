"""用真实 SDK、隔离事务和假上游验证架构接口能够独立替换。"""

from test_capability_runtime import ScriptedModel, execute, response, setup, submit
from test_employee_knowledge import assemble, ready
from test_knowledge_library import create

from app.common.values import digest
from app.resources.knowledge.contracts import Chunk, EvidenceSource
from app.resources.knowledge.schemas import SearchHit, SearchResult
from app.runtime.execution import knowledge_evidence
from app.runtime.execution.models import Run


def test_replacing_model_client_keeps_business_publication(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    acceptance = api_client.app.state.conversation_acceptance
    publish = acceptance.publish_content
    published = []

    def record(db, row, text):
        published.append((row.id, text))
        publish(db, row, text)

    monkeypatch.setattr(acceptance, "publish_content", record)
    for text in ("适配器甲的回答", "适配器乙的回答"):
        accepted = submit(api_client, conversation).json()["response"]
        client = ScriptedModel(responses=[response(text)])
        done = execute(api_client, monkeypatch, client, accepted)
        assert done["status"] == "succeeded" and done["acceptance"] == "accepted"
        assert done["content"] == text and len(client.prompts) == 1
    assert [text for _, text in published] == ["适配器甲的回答", "适配器乙的回答"]


def test_replacing_retrieval_keeps_execution_and_evidence_acceptance(api_client, monkeypatch):
    _, _, employee, conversation = setup(api_client)
    library = create(api_client)["id"]
    document = ready(api_client, library)
    assert assemble(api_client, employee["id"], [library]).status_code == 200
    detail = api_client.get(f"/api/knowledge-bases/{library}/documents/{document['id']}").json()
    chunk = Chunk.model_validate(detail["chunks"][0])
    calls = []

    def replacement(library_id, request, guard):
        with api_client.app.state.database.transaction() as db:
            assert guard(db) is None
        calls.append((library_id, request.question))
        return SearchResult(
            knowledge_base_id=library_id, hits=[SearchHit(rank=1, score=1, chunk=chunk)]
        )

    class RetrievalReplacement:
        query = staticmethod(replacement)

    source_checks = []
    verify = knowledge_evidence.assert_source_evidence

    def source_only(db, value, ids):
        assert isinstance(value, EvidenceSource) and not hasattr(value, "run_id")
        source_checks.append(value.chunk_id)
        verify(db, value, ids)

    monkeypatch.setattr(knowledge_evidence, "assert_source_evidence", source_only)
    monkeypatch.setattr(api_client.app.state.run_knowledge, "search", RetrievalReplacement())
    accepted = submit(api_client, conversation, content="住宿需要什么依据？").json()["response"]
    identifier = "K-" + digest([accepted["id"], library, chunk.id])[:16]
    url = f"/knowledge/sources/{accepted['id']}/{identifier}"
    answer = f"住宿需要发票和逐晚明细。[{identifier}]({url})"
    model = ScriptedModel(
        responses=[
            response("", [{"name": "search_knowledge", "id": "search", "args": {"query": "住宿"}}]),
            response(answer),
        ]
    )
    done = execute(api_client, monkeypatch, model, accepted)
    assert done["status"] == "succeeded" and done["acceptance"] == "accepted"
    assert done["content"] == answer and calls == [(library, "住宿")]
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    evidence = api_client.app.state.knowledge_evidence.references(actor, accepted["id"])
    assert [item.evidence_id for item in evidence] == [identifier]
    assert source_checks and set(source_checks) == {chunk.id}


def test_failed_publication_retries_acceptance_without_executing_model(api_client, monkeypatch):
    _, _, _, conversation = setup(api_client)
    accepted = submit(api_client, conversation).json()["response"]
    acceptance = api_client.app.state.conversation_acceptance
    publish = acceptance.publish_content

    def unavailable(*args):
        raise RuntimeError("isolated publication failure")

    monkeypatch.setattr(acceptance, "publish_content", unavailable)
    model = ScriptedModel(responses=[response("模型已执行完成")])
    pending = execute(api_client, monkeypatch, model, accepted)
    assert pending["status"] == "succeeded" and pending["acceptance"] == "pending"
    with api_client.app.state.database.transaction() as db:
        before = db.get(Run, accepted["id"])
        persisted = (before.model_calls, before.checkpoint_id, before.result_text)

    def unexpected(*args, **kwargs):
        raise AssertionError("acceptance retry attempted to create a model client")

    monkeypatch.setattr("app.infrastructure.llm.factory.create_chat_model", unexpected)
    monkeypatch.setattr(acceptance, "publish_content", publish)
    acceptance.process(accepted["id"])
    acceptance.process(accepted["id"])
    from run_helpers import read_reply

    done = read_reply(api_client, accepted["id"])
    assert done["content"] == "模型已执行完成" and done["acceptance"] == "accepted"
    assert len(model.prompts) == 1
    with api_client.app.state.database.transaction() as db:
        after = db.get(Run, accepted["id"])
        assert (after.model_calls, after.checkpoint_id, after.result_text) == persisted


def test_file_registration_returns_a_frozen_value_in_the_callers_transaction(api_client):
    from dataclasses import FrozenInstanceError

    import pytest

    from app.resources.files.contracts import FileMetadata
    from app.resources.files.models import StoredFile

    state = api_client.app.state
    actor = state.auth.resolve(api_client.cookies.get("app_session"))
    prepared = state.files.prepare("owned.txt", b"isolated bytes")
    with pytest.raises(RuntimeError, match="rollback"):
        with state.database.transaction() as db:
            value = state.files.register(db, actor.user_id, prepared)
            assert isinstance(value, FileMetadata)
            with pytest.raises(FrozenInstanceError):
                value.name = "foreign mutation"
            raise RuntimeError("rollback")
    with state.database.transaction() as db:
        assert db.get(StoredFile, value.id) is None
