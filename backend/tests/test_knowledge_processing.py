"""Durability, atomic file publication, cancellation and scope, with no model calls."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import select, text
from test_knowledge_library import create, library_owner, process, upload

from app.auth.actor import Actor
from app.errors import NotFoundError
from app.knowledge.models import LibraryDocument, ProcessingItem
from app.knowledge.worker import KnowledgeWorker
from app.values import utc_now


def detail(client, kb, doc):
    return client.get(f"/api/knowledge-bases/{kb}/documents/{doc}").json()


def hits(client, kb):
    return client.post(f"/api/knowledge-bases/{kb}/search", json={"question": "住宿 高铁"}).json()[
        "hits"
    ]


def test_original_is_readable_but_not_searchable_until_explicit_processing(api_client):
    kb = create(api_client)["id"]
    doc = upload(api_client, kb).json()
    assert not doc["keyword_ready"] and doc["processing_state"] == "pending"
    assert detail(api_client, kb, doc["id"])["document"] is None
    assert (
        api_client.get(f"/api/knowledge-bases/{kb}/documents/{doc['id']}/original").status_code
        == 200
    )
    assert hits(api_client, kb) == []
    request = str(uuid4())
    first = process(api_client, kb, [doc["id"]], request_id=request, run=False).json()
    second = process(api_client, kb, [doc["id"]], request_id=request, run=False).json()
    assert first["id"] == second["id"]
    assert len(first["items"]) == 1
    conflict = api_client.post(
        f"/api/knowledge-bases/{kb}/processing",
        json={"client_request_id": request, "document_ids": [doc["id"]], "reprocess": True},
    )
    assert conflict.status_code == 409
    assert api_client.app.state.knowledge.processing.run_next()
    assert detail(api_client, kb, doc["id"])["keyword_ready"] and hits(api_client, kb)


def test_effective_rule_validation_revision_guard_and_frozen_job(api_client):
    base = create(api_client)
    kb = base["id"]
    doc = upload(api_client, kb, "# 住宿\n" + "住宿报销规则。" * 100).json()
    payload = {
        "expected_revision": base["revision"],
        "name": base["name"],
        "description": "范围",
        "chunk_size": 100,
        "chunk_overlap": None,
    }
    assert api_client.patch(f"/api/knowledge-bases/{kb}", json=payload).status_code == 422
    payload["chunk_overlap"] = 10
    updated = api_client.patch(f"/api/knowledge-bases/{kb}", json=payload)
    assert updated.status_code == 200
    job = process(api_client, kb, [doc["id"]], run=False).json()
    assert job["rules"] == {
        "chunk_size": 100,
        "chunk_overlap": 10,
        "min_section_chars": 90,
        "split_version": 2,
    }
    assert api_client.patch(f"/api/knowledge-bases/{kb}", json=payload).status_code == 409
    payload.update(expected_revision=updated.json()["revision"], chunk_size=300, chunk_overlap=20)
    assert api_client.patch(f"/api/knowledge-bases/{kb}", json=payload).status_code == 200
    api_client.app.state.knowledge.processing.run_next()
    result = detail(api_client, kb, doc["id"])
    assert result["processing_rules"] == job["rules"]
    assert max(len(c["text"]) for c in result["chunks"]) <= 100


def test_each_successful_file_is_queryable_without_waiting_for_batch(api_client, monkeypatch):
    import app.knowledge.processing as processing

    kb = create(api_client)["id"]
    docs = [
        upload(api_client, kb, "# 住宿\n" + word, f"{word}.md").json()
        for word in ("住宿甲", "住宿乙", "坏文件")
    ]
    native = processing.text_document

    def parse(data, id, filename):
        if "坏文件" in filename:
            raise ValueError("private-parser-body")
        return native(data, id, filename)

    monkeypatch.setattr(processing, "text_document", parse)
    job = process(api_client, kb, run=False).json()
    worker = api_client.app.state.knowledge.processing
    assert worker.run_next()
    snapshot = api_client.get(f"/api/knowledge-bases/{kb}/processing/{job['id']}").json()
    if any(item["status"] == "succeeded" for item in snapshot["items"]):
        assert hits(api_client, kb)
    while worker.run_next():
        pass
    result = api_client.get(f"/api/knowledge-bases/{kb}/processing/{job['id']}").json()
    assert result["status"] == "partial"
    assert [i["status"] for i in result["items"]].count("succeeded") == 2
    assert "private-parser-body" not in str(result)
    assert len(hits(api_client, kb)) == 2
    monkeypatch.setattr(processing, "text_document", native)
    retried = process(api_client, kb, [docs[2]["id"]]).json()
    assert retried["status"] == "succeeded" and len(hits(api_client, kb)) == 3


def test_failed_reprocess_keeps_active_text_and_fts(api_client, monkeypatch):
    import app.knowledge.processing as processing

    kb = create(api_client)["id"]
    doc = upload(api_client, kb).json()
    process(api_client, kb)
    before = detail(api_client, kb, doc["id"])
    original_hits = hits(api_client, kb)
    monkeypatch.setattr(
        processing,
        "split_document",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("secret")),
    )
    result = process(api_client, kb, [doc["id"]], reprocess=True).json()
    assert result["status"] == "failed"
    after = detail(api_client, kb, doc["id"])
    assert after["processing_state"] == "failed" and after["keyword_ready"]
    assert after["chunks"] == before["chunks"] and hits(api_client, kb) == original_hits


def test_delete_during_work_prevents_late_republication(api_client, monkeypatch):
    import app.knowledge.processing as processing

    kb = create(api_client)["id"]
    keep = upload(api_client, kb, "# 住宿\n住宿保留", "keep.md").json()
    process(api_client, kb)
    target = upload(api_client, kb).json()
    service = api_client.app.state.knowledge
    actor = Actor(
        "user", "", library_owner(service, kb), "admin", "admin", utc_now() + timedelta(hours=1)
    )
    native = processing.split_document

    def split(*args, **kwargs):
        chunks = native(*args, **kwargs)
        service.remove(actor, kb, target["id"])
        return chunks

    monkeypatch.setattr(processing, "split_document", split)
    job = process(api_client, kb).json()
    assert job["status"] == "cancelled"
    assert api_client.get(f"/api/knowledge-bases/{kb}/documents/{target['id']}").status_code == 404
    assert hits(api_client, kb)[0]["chunk"]["document_id"] == keep["id"]


def test_cancel_has_no_side_effect_on_published_content_and_scope_is_enforced(api_client):
    kb = create(api_client)["id"]
    doc = upload(api_client, kb).json()
    process(api_client, kb)
    queued = process(api_client, kb, [doc["id"]], reprocess=True, run=False).json()
    service = api_client.app.state.knowledge
    stranger = Actor("user", "", str(uuid4()), "other", "admin", utc_now() + timedelta(hours=1))
    with pytest.raises(NotFoundError):
        service.processing.get(stranger, kb, queued["id"])
    with pytest.raises(NotFoundError):
        service.processing.cancel(stranger, kb, queued["id"])
    result = api_client.post(f"/api/knowledge-bases/{kb}/processing/{queued['id']}/cancel", json={})
    assert result.json()["status"] == "cancelled"
    assert not service.processing.run_next() and hits(api_client, kb)


def test_worker_restart_interrupts_uncertain_item_and_continues_queued(api_client, tmp_path):
    kb = create(api_client)["id"]
    first = upload(api_client, kb).json()
    second = upload(api_client, kb, "# 住宿\n住宿标准", "hotel.md").json()
    queued = process(api_client, kb, run=False).json()
    service = api_client.app.state.knowledge
    with service.database.transaction() as db:
        item = db.scalar(select(ProcessingItem).where(ProcessingItem.document_id == first["id"]))
        item.status = "running"
        db.get(LibraryDocument, first["id"]).processing_state = "processing"

    async def run():
        worker = KnowledgeWorker(service.processing, tmp_path / "knowledge.lock")
        await worker.start()
        duplicate = KnowledgeWorker(service.processing, tmp_path / "knowledge.lock")
        with pytest.raises(BlockingIOError):
            await duplicate.start()
        try:
            for _ in range(100):
                if detail(api_client, kb, second["id"])["keyword_ready"]:
                    break
                await asyncio.sleep(0.02)
        finally:
            await worker.stop()

    asyncio.run(run())
    assert detail(api_client, kb, first["id"])["processing_state"] == "interrupted"
    assert detail(api_client, kb, second["id"])["keyword_ready"]
    job = api_client.get(f"/api/knowledge-bases/{kb}/processing/{queued['id']}").json()
    assert job["status"] == "partial"
    assert process(api_client, kb, [first["id"]]).json()["status"] == "succeeded"


def test_upgrade_preserves_existing_keyword_snapshot(app_config, monkeypatch):
    from legacy_knowledge_helpers import seed_text_library

    from app.knowledge.search import KnowledgeSearch

    database, files, config, actor, kb, doc, chunks = seed_text_library(
        app_config, monkeypatch, "0014"
    )
    try:
        command.upgrade(config, "0020")
        with database.transaction() as db:
            state = db.scalar(
                text("SELECT processing_state FROM knowledge_documents WHERE id=:id"), {"id": doc}
            )
            assert state == "ready"
            assert KnowledgeSearch.lexical_search(db, kb, "高铁", 6)[0].chunk == chunks[0]
            assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        database.close()
