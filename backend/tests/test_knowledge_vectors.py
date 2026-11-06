"""Real SDK/HTTP adapter with synthetic vectors; never a semantic quality benchmark."""

import json
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from alembic import command
from configuration_helpers import patch_current
from fastapi.testclient import TestClient
from test_knowledge_library import create, library_owner, process
from test_knowledge_library import upload as stage_upload

from app.auth.actor import Actor
from app.errors import NotFoundError, PermissionDeniedError
from app.knowledge.models import LibraryVectorIndex
from app.knowledge.schemas import SearchRequest
from app.values import utc_now

KEY = "test-siliconflow-key"


def upload(client, kb, *args, **kwargs):
    response = stage_upload(client, kb, *args, **kwargs)
    if response.status_code == 201:
        process(client, kb, [response.json()["id"]])
    return response


def connection(client):
    response = client.post(
        "/api/model-connections",
        json={
            "name": "硅基知识向量",
            "preset_id": "siliconflow-embedding",
            "api_key": KEY,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def upstream(monkeypatch):
    state = {"requests": [], "status": 200, "dimension": 1024, "after": None}
    native_client = httpx.Client

    def respond(request):
        state["requests"].append(request)
        assert str(request.url) == "https://api.siliconflow.cn/v1/embeddings"
        payload = json.loads(request.content)
        assert payload["model"] == "BAAI/bge-m3"
        assert payload["encoding_format"] == "float"
        assert isinstance(payload["input"], list) and all(
            isinstance(t, str) for t in payload["input"]
        )
        if state["after"]:
            state["after"]()
        if state["status"] != 200:
            return httpx.Response(state["status"], json={"error": {"message": KEY}})
        values = []
        for i, body in enumerate(payload["input"]):
            vector = [0.0] * state["dimension"]
            vector[0 if "住宿" in body or "酒店" in body else 1] = 2.0
            values.append({"index": i, "embedding": vector, "object": "embedding"})
        return httpx.Response(
            200,
            json={
                "data": values,
                "object": "list",
                "model": payload["model"],
                "usage": {"total_tokens": 1, "prompt_tokens": 1},
            },
        )

    class MockClient(native_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr("app.llm.embeddings.httpx.Client", MockClient)
    return state


def build(client, kb, connection_id):
    return client.post(
        f"/api/knowledge-bases/{kb}/vector-index", json={"model_connection_id": connection_id}
    )


def search(client, kb):
    return client.post(
        f"/api/knowledge-bases/{kb}/search",
        json={"question": "酒店能报多少钱", "strategy": "vector"},
    )


def test_embedding_connection_and_real_sdk_product_roundtrip(api_client, upstream):
    model = connection(api_client)
    assert model["capability"] == "embedding" and model["model_id"] == "BAAI/bge-m3"
    assert KEY not in json.dumps(model)
    checked = api_client.post(f"/api/model-connections/{model['id']}/test", json={})
    assert checked.status_code == 200 and checked.json()["ok"]
    assert "api_key" not in api_client.get("/api/knowledge-bases/embedding-connections").text
    assert (
        api_client.post(
            "/api/agents",
            json={"name": "不能聊天", "avatar_id": "admin", "model_connection_id": model["id"]},
        ).status_code
        == 409
    )
    assert (
        patch_current(
            api_client, f"/api/model-connections/{model['id']}", json={"model_id": "other"}
        ).status_code
        == 422
    )
    kb = create(api_client)["id"]
    hotel = upload(api_client, kb, "# 住宿\n住宿上限为每晚 400 元。", "hotel.md").json()
    upload(api_client, kb, "# 交通\n高铁限乘二等座。", "train.md")
    other = create(api_client)["id"]
    upload(api_client, other, "# 住宿\n其他库上限 999 元。", "other.md")
    assert search(api_client, kb).status_code == 409
    built = build(api_client, kb, model["id"])
    assert built.status_code == 200, built.text
    assert built.json()["vector_status"] == "ready" and built.json()["vector_chunk_count"] == 2
    result = search(api_client, kb)
    assert result.status_code == 200, result.text
    hits = result.json()["hits"]
    assert hits[0]["chunk"]["document_id"] == hotel["id"]
    assert (
        hits[0]["score"] == pytest.approx(0)
        and hits[0]["score_kind"] == "cosine_distance_lower_better"
    )
    assert all("999" not in hit["chunk"]["text"] for hit in hits)
    hybrid = api_client.post(
        f"/api/knowledge-bases/{kb}/search",
        json={"question": "住宿", "strategy": "hybrid", "top_k": 1},
    )
    assert hybrid.status_code == 200, hybrid.text
    fused = hybrid.json()
    assert fused["strategy"] == "hybrid" and len(fused["hits"]) == 1
    assert fused["hits"][0]["chunk"]["document_id"] == hotel["id"]
    assert fused["hits"][0]["score_kind"] == "rank_only"
    assert fused["hits"][0]["score"] is None
    # Reading a cited source must not mutate its vectors.
    assert api_client.get(f"/api/knowledge-bases/{kb}/documents/{hotel['id']}").status_code == 200
    assert search(api_client, kb).json()["hits"] == hits
    assert api_client.delete(f"/api/model-connections/{model['id']}").status_code == 409
    assert (
        patch_current(
            api_client,
            f"/api/model-connections/{model['id']}",
            json={"api_key": "rotated-test-key"},
        ).status_code
        == 200
    )
    assert search(api_client, kb).status_code == 200
    TestClient.request(api_client, "DELETE", f"/api/knowledge-bases/{kb}/documents/{hotel['id']}")
    assert api_client.get(f"/api/knowledge-bases/{kb}").json()["vector_status"] == "ready"
    assert search(api_client, kb).status_code == 200
    assert api_client.delete(f"/api/knowledge-bases/{kb}/vector-index").status_code == 204
    assert api_client.delete(f"/api/model-connections/{model['id']}").status_code == 204


@pytest.mark.parametrize(
    "status,dimension,expected",
    [(401, 1024, 503), (429, 1024, 429), (200, 3, 503), (504, 1024, 503)],
)
def test_failed_rebuild_keeps_published_index_without_leaking_provider_body(
    api_client, upstream, status, dimension, expected
):
    model = connection(api_client)
    kb = create(api_client)["id"]
    upload(api_client, kb)
    assert build(api_client, kb, model["id"]).status_code == 200
    upstream.update(status=status, dimension=dimension)
    result = build(api_client, kb, model["id"])
    assert result.status_code == expected, result.text
    assert KEY not in result.text
    assert api_client.get(f"/api/knowledge-bases/{kb}").json()["vector_status"] == "ready"
    upstream.update(status=200, dimension=1024)
    assert search(api_client, kb).status_code == 200


@pytest.mark.parametrize("change", ["documents", "credentials", "disable", "clear"])
def test_publish_rechecks_source_and_model_revisions(api_client, upstream, change):
    model = connection(api_client)
    kb = create(api_client)["id"]
    upload(api_client, kb)
    assert build(api_client, kb, model["id"]).status_code == 200
    service = api_client.app.state.knowledge
    with service.database.transaction() as db:
        generation = db.get(LibraryVectorIndex, kb).generation

    def mutate():
        upstream["after"] = None
        if change == "documents":
            upload(api_client, kb, "新增的资料。", "new.md")
        elif change == "clear":
            api_client.delete(f"/api/knowledge-bases/{kb}/vector-index")
        else:
            patch_current(
                api_client,
                f"/api/model-connections/{model['id']}",
                json={"api_key": "new-key"} if change == "credentials" else {"enabled": False},
            )

    upstream["after"] = mutate
    result = build(api_client, kb, model["id"])
    assert result.status_code == 409, result.text
    with service.database.transaction() as db:
        current = db.get(LibraryVectorIndex, kb)
        assert current is None if change == "clear" else current.generation == generation


def test_owner_permissions_and_build_concurrency_are_enforced_before_upstream(api_client, upstream):
    model = connection(api_client)
    kb = create(api_client)["id"]
    upload(api_client, kb)
    service = api_client.app.state.knowledge
    actor = Actor(
        "user", "", library_owner(service, kb), "member", "member", utc_now() + timedelta(hours=1)
    )
    assert service.vectors.options(actor)[0].id == model["id"]
    for stranger in [
        replace(actor, user_id=str(uuid4()), role="admin"),
        replace(actor, role="guest"),
    ]:
        with pytest.raises((NotFoundError, PermissionDeniedError)):
            service.vectors.build(stranger, kb, model["id"])
    assert upstream["requests"] == []
    assert service.vectors.build_slot.acquire(blocking=False)
    try:
        assert build(api_client, kb, model["id"]).status_code == 409
    finally:
        service.vectors.build_slot.release()
    assert service.vectors.build(actor, kb, model["id"]).vector_status == "ready"
    assert service.search(actor, kb, SearchRequest(question="查询", strategy="vector")).hits


def test_upgrade_from_text_only_preserves_sources(app_config, monkeypatch):
    from legacy_knowledge_helpers import seed_text_library
    from sqlalchemy import text

    from app.knowledge.search import KnowledgeSearch

    database, files, config, actor, kb, document, chunks = seed_text_library(
        app_config, monkeypatch, "0013"
    )
    try:
        command.upgrade(config, "0020")
        with database.transaction() as db:
            file_id = db.scalar(
                text("SELECT file_id FROM knowledge_documents WHERE id=:id"), {"id": document}
            )
            assert db.scalar(text("SELECT count(*) FROM knowledge_vector_indexes")) == 0
            assert KnowledgeSearch.lexical_search(db, kb, "高铁", 6)[0].chunk.id == chunks[0].id
        assert files.read(file_id)
    finally:
        database.close()


def test_rank_fusion_uses_ranks_and_deduplicates_chunks():
    from app.knowledge.contracts import Chunk
    from app.knowledge.retrieval import fuse_rankings
    from app.knowledge.schemas import SearchHit

    def hit(id, rank, score):
        return SearchHit(
            rank=rank,
            score=score,
            chunk=Chunk(
                id=id,
                document_id="d",
                document_version="v",
                title=id,
                locator="",
                start=0,
                end=1,
                spans=(),
                text=id,
                index_text=id,
            ),
        )

    lexical = [hit("a", 1, -10000), hit("b", 2, -0.001)]
    semantic = [hit("b", 1, 0.9), hit("c", 2, 0.8)]
    result = fuse_rankings([lexical, semantic], 3)
    assert [h.chunk.id for h in result] == ["b", "a", "c"]
    assert result[0].score is None
    assert [h.rank for h in result] == [1, 2, 3]
    assert all(h.score_kind == "rank_only" for h in result)
    assert fuse_rankings([[], []], 3) == []
    tied = fuse_rankings([[hit("b", 1, -1)], [hit("a", 1, 0.9)]], 1)
    assert tied[0].chunk.id == "b"
