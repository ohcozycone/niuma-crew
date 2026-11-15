"""Durability and billing boundaries of asynchronous vector builds (fake upstream only)."""

import json
from uuid import uuid4

from sqlalchemy import delete, select
from test_knowledge_library import create, process
from test_knowledge_vectors import build, connection, submit, upload
from test_knowledge_vectors import upstream as upstream

from app.auth.models import User
from app.resources.knowledge.models import LibraryVectorIndex, VectorEmbedding, VectorJob


def job(client, kb, id):
    response = client.get(f"/api/knowledge-bases/{kb}/vector-jobs/{id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_enqueue_is_durable_idempotent_and_never_calls_provider(api_client, upstream):
    kb = create(api_client)["id"]
    upload(api_client, kb)
    model = connection(api_client)["id"]
    request = str(uuid4())
    first = submit(api_client, kb, model, request)
    assert first.status_code == 202 and first.json()["status"] == "queued"
    assert upstream["requests"] == []
    assert submit(api_client, kb, model, request).json() == first.json()
    assert submit(api_client, kb, model).status_code == 409
    api_client.app.state.rate_limiter.entries.clear()
    other = str(uuid4())
    assert submit(api_client, kb, other, request).status_code == 409
    assert api_client.delete(f"/api/model-connections/{model}").status_code == 409
    service = api_client.app.state.knowledge_vectors
    service.recover()
    assert job(api_client, kb, first.json()["id"])["status"] == "queued"
    assert service.run_next()
    assert job(api_client, kb, first.json()["id"])["status"] == "succeeded"
    assert not service.run_next()


def test_unchanged_and_rechunked_text_is_reused_and_only_new_content_is_embedded(
    api_client, upstream
):
    kb = create(api_client)["id"]
    document = upload(api_client, kb, "# 住宿\n酒店报销上限400元。", "hotel.md").json()
    model = connection(api_client)["id"]
    assert build(api_client, kb, model).json()["vector_status"] == "ready"
    upstream["requests"].clear()
    # Simulate an existing installation: no new checkpoint table contents yet.
    with api_client.app.state.database.transaction() as db:
        db.execute(delete(VectorEmbedding))
    assert build(api_client, kb, model).json()["vector_status"] == "ready"
    assert upstream["requests"] == []
    process(
        api_client,
        kb,
        [document["id"]],
        rules={"chunk_size": 900, "chunk_overlap": 120, "min_section_chars": 200},
    )
    assert build(api_client, kb, model).json()["vector_status"] == "ready"
    assert upstream["requests"] == []
    api_client.app.state.rate_limiter.entries.clear()
    upload(api_client, kb, "# 交通\n高铁二等座。", "train.md")
    assert build(api_client, kb, model).json()["vector_status"] == "ready"
    inputs = [
        text for request in upstream["requests"] for text in json.loads(request.content)["input"]
    ]
    assert len(inputs) == 1 and "高铁" in inputs[0]


def test_completed_batches_survive_failure_restart_and_retry(api_client, upstream):
    kb = create(api_client)["id"]
    text = "\n\n".join(f"# Section {i}\n" + f"unique-section-{i} content " * 25 for i in range(20))
    upload(api_client, kb, text)
    model = connection(api_client)["id"]
    queued = submit(api_client, kb, model).json()
    assert queued["chunk_count"] > 8

    def fail_second_batch():
        if len(upstream["requests"]) == 2:
            upstream["status"] = 429

    upstream["after"] = fail_second_batch
    vectors = api_client.app.state.knowledge_vectors
    vectors.run_next()
    first = job(api_client, kb, queued["id"])
    assert first["status"] == "failed" and first["completed_count"] == 8
    assert "test-siliconflow-key" not in json.dumps(first)
    # Crash recovery never retries an unknown in-flight provider response automatically.
    with api_client.app.state.database.transaction() as db:
        db.get(VectorJob, queued["id"]).status = "running"
    vectors.store.close()
    vectors.reconcile()
    vectors.recover()
    assert job(api_client, kb, queued["id"])["status"] == "interrupted"
    assert not vectors.run_next()
    upstream.update(status=200, after=None)
    upstream["requests"].clear()
    retried = submit(api_client, kb, model).json()
    vectors.run_next()
    result = job(api_client, kb, retried["id"])
    assert result["status"] == "succeeded" and result["reused_count"] == 8
    assert result["completed_count"] == result["chunk_count"]
    assert (
        sum(len(json.loads(r.content)["input"]) for r in upstream["requests"])
        == result["chunk_count"] - 8
    )


def test_cancel_during_provider_call_cannot_publish_or_start_next_batch(api_client, upstream):
    kb = create(api_client)["id"]
    upload(api_client, kb)
    model = connection(api_client)["id"]
    build(api_client, kb, model)
    with api_client.app.state.database.transaction() as db:
        old_generation = db.get(LibraryVectorIndex, kb).generation
    upload(api_client, kb, "新增资料必须取消。", "new.md")
    queued = submit(api_client, kb, model).json()
    upstream["requests"].clear()

    def cancel():
        upstream["after"] = None
        response = api_client.post(
            f"/api/knowledge-bases/{kb}/vector-jobs/{queued['id']}/cancel", json={}
        )
        assert response.json()["status"] == "cancelled"

    upstream["after"] = cancel
    api_client.app.state.knowledge_vectors.run_next()
    assert job(api_client, kb, queued["id"])["status"] == "cancelled"
    assert len(upstream["requests"]) == 1
    with api_client.app.state.database.transaction() as db:
        assert db.get(LibraryVectorIndex, kb).generation == old_generation
    assert api_client.get(f"/api/knowledge-bases/{kb}").json()["vector_status"] == "partial"


def test_revoked_authorization_fails_before_provider_and_clear_discards_checkpoints(
    api_client, upstream
):
    kb = create(api_client)["id"]
    upload(api_client, kb)
    model = connection(api_client)["id"]
    queued = submit(api_client, kb, model).json()
    state = api_client.app.state
    with state.database.transaction() as db:
        user = db.scalar(select(User))
        user.is_active = False
    state.knowledge_vectors.run_next()
    with state.database.transaction() as db:
        row = db.get(VectorJob, queued["id"])
        assert row.status == "failed" and row.error_code == "actor_session_invalid"
        db.scalar(select(User)).is_active = True
    assert upstream["requests"] == []
    build(api_client, kb, model)
    assert api_client.delete(f"/api/knowledge-bases/{kb}/vector-index").status_code == 204
    with state.database.transaction() as db:
        assert list(db.scalars(select(VectorEmbedding))) == []
    upstream["requests"].clear()
    build(api_client, kb, model)
    assert len(upstream["requests"]) == 1


def test_model_space_change_never_reuses_old_vectors(api_client, upstream, monkeypatch):
    kb = create(api_client)["id"]
    upload(api_client, kb)
    model = connection(api_client)["id"]
    build(api_client, kb, model)
    monkeypatch.setattr(
        "app.resources.knowledge.vectors.embedding_fingerprint",
        lambda config: "changed-model-space",
    )
    upstream["requests"].clear()
    build(api_client, kb, model)
    assert len(upstream["requests"]) == 1


def test_worker_shutdown_preserves_live_generation_and_stops_new_batches(api_client, upstream):
    kb = create(api_client)["id"]
    upload(api_client, kb)
    model = connection(api_client)["id"]
    queued = submit(api_client, kb, model).json()
    vectors = api_client.app.state.knowledge_vectors
    upstream["after"] = vectors.stopping.set
    vectors.run_next()
    assert job(api_client, kb, queued["id"])["status"] == "interrupted"
    assert api_client.get(f"/api/knowledge-bases/{kb}").json()["vector_status"] == "not_built"
    assert len(upstream["requests"]) == 1


def test_additive_migration_preserves_existing_documents_and_live_index(api_client, upstream):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    from app.resources.knowledge.models import LibraryChunk, LibraryDocument

    kb = create(api_client)["id"]
    upload(api_client, kb)
    model = connection(api_client)["id"]
    build(api_client, kb, model)
    state = api_client.app.state
    with state.database.transaction() as db:
        generation = db.get(LibraryVectorIndex, kb).generation
        documents = list(db.scalars(select(LibraryDocument.id)))
        chunks = list(db.scalars(select(LibraryChunk.id)))
    names = state.knowledge_vectors.store.names()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.downgrade(config, "0028")
    command.upgrade(config, "0029")
    command.check(config)
    with state.database.transaction() as db:
        assert db.get(LibraryVectorIndex, kb).generation == generation
        assert list(db.scalars(select(LibraryDocument.id))) == documents
        assert list(db.scalars(select(LibraryChunk.id))) == chunks
        assert list(db.scalars(select(VectorJob))) == []
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    assert state.knowledge_vectors.store.names() == names
    upstream["requests"].clear()
    build(api_client, kb, model)
    assert upstream["requests"] == []


def test_knowledge_worker_executes_vector_queue_and_releases_lock(api_client, upstream, tmp_path):
    import asyncio

    from app.resources.knowledge.worker import KnowledgeWorker

    kb = create(api_client)["id"]
    upload(api_client, kb)
    model = connection(api_client)["id"]
    submitted = submit(api_client, kb, model).json()
    state = api_client.app.state

    async def run():
        worker = KnowledgeWorker(
            state.knowledge_processing,
            tmp_path / "knowledge.lock",
            reconcile=state.knowledge_vectors.reconcile,
            vectors=state.knowledge_vectors,
        )
        await worker.start()
        try:
            for _ in range(100):
                if job(api_client, kb, submitted["id"])["status"] == "succeeded":
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError("Vector queue was not consumed by the knowledge worker")
        finally:
            await worker.stop()
        assert worker.lock is None and worker.task is None

    asyncio.run(run())
