import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_employee_knowledge import agent, assemble, member, ready, run
from test_knowledge_library import create

from app.api.dependencies import get_actor, get_knowledge_evidence
from app.api.routes.knowledge import source_router
from app.auth.actor import Actor
from app.common.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.common.values import utc_now
from app.resources.knowledge.models import LibraryChunk
from app.runtime.execution.evidence_models import RunKnowledgeEvidence
from app.runtime.execution.models import Run


def prepared(client, *, owner=None):
    employee = agent(client)
    kb = create(client)["id"]
    ready(client, kb)
    assert assemble(client, employee, [kb]).status_code == 200
    run_id, snapshot = run(client, employee, owner=owner)
    service = client.app.state
    result = service.run_knowledge.call(run_id, "search_knowledge", {"query": "住宿"})
    assert result.status == "succeeded", result.content
    hit = json.loads(result.content)["hits"][0]
    return service, employee, kb, run_id, snapshot, hit


def test_member_reads_only_registered_run_evidence_and_not_library(api_client):
    with api_client.app.state.database.transaction() as db:
        viewer = member(db)
        stranger = member(db)
    service, employee, kb, run_id, snapshot, hit = prepared(api_client, owner=viewer.user_id)
    result = service.knowledge_evidence.preview(viewer, run_id, hit["evidence_id"])
    assert "住宿" in result.content and result.source_url == hit["source_url"]
    with pytest.raises(PermissionDeniedError):
        service.knowledge_libraries.get(viewer, kb)
    with pytest.raises(NotFoundError):
        service.knowledge_evidence.preview(stranger, run_id, hit["evidence_id"])
    with pytest.raises(NotFoundError):
        service.knowledge_evidence.preview(viewer, run_id, "K-0000000000000000")
    assert len(service.knowledge_evidence.references(viewer, run_id)) == 1
    assert assemble(api_client, employee, []).status_code == 200
    assert (
        service.knowledge_evidence.preview(viewer, run_id, hit["evidence_id"]).content
        == result.content
    )
    with pytest.raises(ConflictError):
        service.run_knowledge.call(
            run_id, "read_knowledge_source", {"evidence_id": hit["evidence_id"]}
        )
    with service.database.transaction() as db:
        chunk = db.get(LibraryChunk, hit["chunk_id"])
        chunk.snapshot = {**chunk.snapshot, "text": "已重切的不同内容"}
    with pytest.raises(ConflictError):
        service.knowledge_evidence.preview(viewer, run_id, hit["evidence_id"])


def test_run_source_http_endpoint_and_guest_denial(api_client):
    service, _, _, run_id, _, hit = prepared(api_client)
    path = f"/api/runs/{run_id}/knowledge-evidence/{hit['evidence_id']}"
    app = FastAPI()
    app.include_router(source_router)
    with service.database.transaction() as db:
        owner = db.get(Run, run_id).owner_user_id
    actor = Actor("user", "", owner, "admin", "admin", utc_now() + timedelta(hours=1))
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_knowledge_evidence] = lambda: service.knowledge_evidence
    with TestClient(app) as client:
        result = client.get(path)
        assert result.status_code == 200, result.text
        assert result.json()["source_url"].startswith("/knowledge/sources/")
        assert client.get(path + "?offset=2001").status_code == 422
        assert len(client.get(f"/api/runs/{run_id}/knowledge-evidence").json()) == 1
    guest = Actor("guest", "", None, None, "guest", utc_now() + timedelta(hours=1))
    with pytest.raises(PermissionDeniedError):
        service.knowledge_evidence.preview(guest, run_id, hit["evidence_id"])


@pytest.mark.parametrize("mismatch", ["owner", "thread", "legacy_user"])
def test_history_does_not_expand_scope_or_cross_owner_thread(api_client, mismatch):
    service, employee, kb, source_id, snapshot, hit = prepared(api_client)
    with service.database.transaction() as db:
        source = db.get(Run, source_id)
        source.status = "succeeded"
        source.finished_at = utc_now()
        owner, thread = source.owner_user_id, source.thread_id
        captured = snapshot["knowledge"]
        if mismatch == "legacy_user":
            source.config_snapshot = {
                **snapshot,
                "knowledge": {**captured, "user_id": str(uuid4())},
            }
        items = service.knowledge_evidence.capture_history(
            db,
            captured,
            [(source_id, f"[{hit['evidence_id']}]({hit['source_url']})")],
            18000,
            owner_user_id=str(uuid4()) if mismatch == "owner" else owner,
            thread_id=str(uuid4()) if mismatch == "thread" else thread,
        )
        assert items == []


def test_legacy_history_is_rebound_without_retired_settings_and_keeps_exact_links(api_client):
    service, employee, kb, source_id, snapshot, hit = prepared(api_client)
    with service.database.transaction() as db:
        original = db.get(Run, source_id)
        original.status = "succeeded"
        original.finished_at = utc_now()
        owner, thread = original.owner_user_id, original.thread_id
        original.config_snapshot = {
            **snapshot,
            "knowledge": {**snapshot["knowledge"], "user_id": owner},
        }
        evidence = db.get(RunKnowledgeEvidence, (source_id, hit["evidence_id"]))
        citation = f"[{hit['evidence_id']}]({service.knowledge_evidence.legacy_url(evidence)})"
    previous = source_id
    for _ in range(2):
        target_id, target_snapshot = run(api_client, employee)
        with service.database.transaction() as db:
            target = db.get(Run, target_id)
            target.thread_id = thread
            items = service.knowledge_evidence.capture_history(
                db,
                target_snapshot["knowledge"],
                [(previous, citation)],
                18000,
                owner_user_id=owner,
                thread_id=thread,
            )
            assert len(items) == 1
            target.config_snapshot = {
                **target_snapshot,
                "knowledge": {**target_snapshot["knowledge"], "history_evidence": items},
            }
            service.knowledge_evidence.bind_history(db, target)
            citation = service.knowledge_evidence.clean_history(citation, items)
        assert hit["source_url"] in citation
        assert service.knowledge_evidence.finalize_answer(target_id, citation) == citation
        with service.database.transaction() as db:
            db.get(Run, target_id).status = "succeeded"
            db.get(Run, target_id).finished_at = utc_now()
        previous = target_id
