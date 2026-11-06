"""Real Chroma persistence and publication failures with synthetic embedding responses."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import select
from test_knowledge_library import create, library_owner
from test_knowledge_vectors import build, connection, upload
from test_knowledge_vectors import upstream as upstream

from app.auth.actor import Actor
from app.errors import ConflictError
from app.knowledge.models import LibraryVectorIndex, LibraryVectorMembership
from app.knowledge.schemas import SearchRequest
from app.knowledge.vector_store import KnowledgeVectorStore
from app.values import utc_now


@pytest.fixture
def indexed(api_client, upstream):
    model = connection(api_client)
    kb = create(api_client)["id"]
    hotel = upload(api_client, kb, "# 住宿\n住宿每晚四百元。", "hotel.md").json()
    train = upload(api_client, kb, "# 交通\n高铁二等座。", "train.md").json()
    assert build(api_client, kb, model["id"]).status_code == 200
    service = api_client.app.state.knowledge
    actor = Actor(
        "user", "", library_owner(service, kb), "admin", "admin", utc_now() + timedelta(hours=1)
    )
    return service, actor, kb, model["id"], hotel, train


def current_name(service, kb):
    with service.database.transaction() as db:
        return db.get(LibraryVectorIndex, kb).collection_name


def test_restart_reopens_persisted_vectors_without_reembedding(indexed, upstream):
    service, actor, kb, _, _, _ = indexed
    vectors = service.vectors
    expected = service.search(actor, kb, SearchRequest(question="酒店", strategy="vector"))
    count = len(upstream["requests"])
    directory = vectors.store.directory
    name = current_name(service, kb)
    vectors.store.close()
    # A fresh interpreter must read the on-disk index, independent of Chroma's
    # process-level client cache and of the parent's embedding test transport.
    import json
    import subprocess
    import sys

    script = """
import json, sys
from pathlib import Path
from app.knowledge.vector_store import KnowledgeVectorStore
store = KnowledgeVectorStore(Path(sys.argv[1]))
try:
    result = store.query(sys.argv[2], [1.0] + [0.0] * 1023, json.loads(sys.argv[3]), 2)
    print(json.dumps([id for id, distance in result]))
finally:
    store.close()
"""
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(directory),
            name,
            json.dumps([hit.chunk.id for hit in expected.hits]),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout) == [hit.chunk.id for hit in expected.hits]
    vectors.store = KnowledgeVectorStore(directory)
    vectors.reconcile()
    actual = service.search(actor, kb, SearchRequest(question="酒店", strategy="vector"))
    assert actual == expected
    assert len(upstream["requests"]) == count + 1  # One query embedding, no document requests.


def test_second_store_cannot_write_the_same_local_directory(indexed):
    service, *_ = indexed
    duplicate = KnowledgeVectorStore(service.vectors.store.directory)
    try:
        with pytest.raises(BlockingIOError):
            duplicate.names()
    finally:
        duplicate.close()


def test_incomplete_collection_never_replaces_published_index(indexed, upstream, monkeypatch):
    service, actor, kb, model, *_ = indexed
    store = service.vectors.store
    old = current_name(service, kb)
    original = store.build

    def fail(*args):
        original(*args)
        raise RuntimeError("injected write failure")

    monkeypatch.setattr(store, "build", fail)
    with pytest.raises(RuntimeError, match="injected"):
        service.vectors.build(actor, kb, model)
    assert current_name(service, kb) == old
    assert store.names() == {old}
    assert service.search(actor, kb, SearchRequest(question="酒店", strategy="vector")).hits


def test_commit_failure_removes_unpublished_collection(indexed, monkeypatch):
    service, actor, kb, model, *_ = indexed
    store = service.vectors.store
    old = current_name(service, kb)
    transaction = service.database.transaction
    original = store.build
    fail = False

    def stage(*args):
        nonlocal fail
        original(*args)
        fail = True

    @contextmanager
    def rejecting_transaction():
        nonlocal fail
        with transaction() as db:
            yield db
            if fail:
                fail = False
                raise RuntimeError("injected commit failure")

    monkeypatch.setattr(store, "build", stage)
    monkeypatch.setattr(service.database, "transaction", rejecting_transaction)
    with pytest.raises(RuntimeError, match="commit failure"):
        service.vectors.build(actor, kb, model)
    assert current_name(service, kb) == old
    assert store.names() == {old}


def test_rebuild_keeps_collection_pinned_until_old_query_finishes(indexed, upstream):
    service, actor, kb, model, *_ = indexed
    old = current_name(service, kb)

    def rebuild():
        upstream["after"] = None
        service.vectors.build(actor, kb, model)
        assert current_name(service, kb) != old
        assert old in service.vectors.store.names()

    upstream["after"] = rebuild
    with pytest.raises(ConflictError, match="检索期间"):
        service.search(actor, kb, SearchRequest(question="酒店", strategy="vector"))
    assert old not in service.vectors.store.names()


def test_deleted_members_are_excluded_even_when_physical_cleanup_fails(
    indexed, api_client, monkeypatch
):
    service, actor, kb, _, hotel, train = indexed
    store = service.vectors.store
    name = current_name(service, kb)
    original = store.prune

    def fail(*args):
        raise RuntimeError("physical deletion unavailable")

    monkeypatch.setattr(store, "prune", fail)
    service.remove(actor, kb, hotel["id"])
    assert store.client.get_collection(name, embedding_function=None).count() == 2
    result = service.search(actor, kb, SearchRequest(question="酒店", strategy="vector"))
    assert {hit.chunk.document_id for hit in result.hits} == {train["id"]}
    monkeypatch.setattr(store, "prune", original)
    service.vectors.reconcile()
    assert store.client.get_collection(name, embedding_function=None).count() == 1


def test_partial_coverage_survives_new_documents_and_reprocessing(indexed, api_client):
    from test_knowledge_library import process

    service, actor, kb, _, hotel, train = indexed
    upload(api_client, kb, "# 餐饮\n餐饮每日一百元。", "meal.md")
    assert service.get(actor, kb).vector_status == "partial"
    assert service.get(actor, kb).vector_chunk_count == 2
    process(api_client, kb, [hotel["id"]], reprocess=True)
    assert service.get(actor, kb).vector_chunk_count == 1
    result = service.search(actor, kb, SearchRequest(question="酒店", strategy="vector"))
    assert {hit.chunk.document_id for hit in result.hits} == {train["id"]}


def test_startup_cleans_orphans_and_marks_missing_index_for_rebuild(indexed):
    service, actor, kb, *_ = indexed
    store = service.vectors.store
    orphan = "niuma_kb_unpublished_orphan"
    store.client.create_collection(orphan, embedding_function=None)
    service.vectors.reconcile()
    assert orphan not in store.names()
    store.client.delete_collection(current_name(service, kb))
    service.vectors.reconcile()
    assert service.get(actor, kb).vector_status == "not_built"
    with service.database.transaction() as db:
        assert list(db.scalars(select(LibraryVectorMembership))) == []


def test_no_default_embedding_and_query_bytes_preserved(indexed, api_client, upstream):
    _, _, kb, *_ = indexed
    before = len(upstream["requests"])
    import json

    query = "还需要提供 MCP OAuth 的授权材料吗？"
    response = api_client.post(
        f"/api/knowledge-bases/{kb}/search", json={"question": query, "strategy": "hybrid"}
    )
    assert response.status_code == 200
    requests = upstream["requests"][before:]
    assert len(requests) == 1
    assert json.loads(requests[0].content)["input"] == [query]
    assert all(hit["score"] is None for hit in response.json()["hits"])


def test_parallel_queries_keep_consistent_results(indexed, upstream):
    service, actor, kb, *_ = indexed
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: service.search(
                    actor, kb, SearchRequest(question="酒店", strategy="hybrid")
                ),
                range(8),
            )
        )
    assert all(result == results[0] for result in results)
    assert not service.vectors.store._readers


@pytest.mark.parametrize("mode", ["on_demand", "always"])
def test_real_agent_uses_chroma_hybrid_path(api_client, upstream, monkeypatch, mode):
    from test_capability_runtime import execute
    from test_conversations import send
    from test_employee_knowledge_runtime import KnowledgeModel, configure

    _, conversation, base, document, _ = configure(api_client, mode=mode)
    model = connection(api_client)
    assert build(api_client, base["id"], model["id"]).status_code == 200
    before = len(upstream["requests"])
    accepted = send(api_client, conversation, "本公司住宿标准是什么？").json()["response"]
    result = execute(api_client, monkeypatch, KnowledgeModel(mode=mode), accepted)
    assert result["status"] == "succeeded", result
    assert f"/knowledge/{base['id']}/documents/{document['id']}?chunk=" in result["content"]
    assert len(upstream["requests"]) == before + 1


def test_0023_discards_vectors_and_preserves_original_and_keyword_data(app_config, monkeypatch):
    import json

    from alembic import command
    from legacy_knowledge_helpers import seed_text_library
    from sqlalchemy import text

    from app.model_connections.models import ModelConnection
    from app.values import new_uuid

    database, files, config, _, kb, doc, chunks = seed_text_library(app_config, monkeypatch, "0022")
    try:
        model_id = new_uuid()
        with database.transaction() as db:
            db.add(
                ModelConnection(
                    id=model_id,
                    name="旧向量连接",
                    preset_id="siliconflow-embedding",
                    model_id="BAAI/bge-m3",
                    capability="embedding",
                    encrypted_api_key="fixture-not-a-real-key",
                )
            )
            db.flush()
            db.execute(
                text(
                    "INSERT INTO knowledge_vector_indexes VALUES (:kb,:model,1,:generation,'old-source',1)"
                ),
                {"kb": kb, "model": model_id, "generation": new_uuid()},
            )
            db.execute(
                text("INSERT INTO knowledge_vectors VALUES (:chunk,:kb,:vector)"),
                {"chunk": chunks[0].id, "kb": kb, "vector": json.dumps([1.0] + [0.0] * 1023)},
            )
            before = db.execute(
                text("SELECT snapshot,file_id FROM knowledge_documents WHERE id=:id"), {"id": doc}
            ).one()
        command.upgrade(config, "head")
        with database.transaction() as db:
            after = db.execute(
                text("SELECT snapshot,file_id FROM knowledge_documents WHERE id=:id"), {"id": doc}
            ).one()
            assert before == after
            assert db.scalar(text("SELECT count(*) FROM knowledge_vector_indexes")) == 0
            assert db.scalar(text("SELECT count(*) FROM knowledge_vector_memberships")) == 0
            assert db.scalar(text("SELECT count(*) FROM knowledge_fts")) == 1
            assert db.execute(text("PRAGMA foreign_key_check")).all() == []
        assert files.read(after.file_id)
    finally:
        database.close()
