"""Product ingestion against migrated SQLite, real FTS5 and persisted originals."""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.auth.actor import Actor
from app.errors import NotFoundError
from app.files.models import StoredFile
from app.knowledge.models import KnowledgeBase, LibraryDocument
from app.knowledge.schemas import SearchRequest
from app.knowledge.service import KnowledgeService, retained_file_ids
from app.values import utc_now


def create(client, name="测试资料"):
    response = client.post(
        "/api/knowledge-bases", json={"name": name, "client_request_id": str(uuid4())}
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(
    client,
    kb,
    data="# 交通\n高铁一等座须在购票前取得特别批准。",
    name="交通规则.md",
    request_id=None,
):
    return client.post(
        f"/api/knowledge-bases/{kb}/documents",
        params={"name": name, "client_request_id": request_id or str(uuid4())},
        content=data.encode() if isinstance(data, str) else data,
        headers={"Content-Type": "application/octet-stream"},
    )


def library_owner(service, id):
    with service.database.transaction() as session:
        return session.get(KnowledgeBase, id).owner_user_id


def process(client, kb, documents=None, reprocess=False, request_id=None, run=True):
    response = client.post(
        f"/api/knowledge-bases/{kb}/processing",
        json={
            "client_request_id": request_id or str(uuid4()),
            "document_ids": documents,
            "reprocess": reprocess,
        },
    )
    assert response.status_code == 202, response.text
    if run:
        while client.app.state.knowledge.processing.run_next():
            pass
    return client.get(f"/api/knowledge-bases/{kb}/processing/{response.json()['id']}")


def test_upload_source_search_reopen_and_remove(api_client):
    library = create(api_client)
    id = library["id"]
    result = upload(api_client, id)
    assert result.status_code == 201, result.text
    doc = result.json()
    assert doc["chunk_count"] == 0 and doc["processing_state"] == "pending"
    assert process(api_client, id).json()["status"] == "succeeded"
    detail = api_client.get(f"/api/knowledge-bases/{id}/documents/{doc['id']}").json()
    chunk = detail["chunks"][0]
    assert detail["document"]["text"][chunk["start"] : chunk["end"]] == chunk["text"]
    original = api_client.get(f"/api/knowledge-bases/{id}/documents/{doc['id']}/original")
    assert original.content.decode() == detail["document"]["text"]
    found = api_client.post(
        f"/api/knowledge-bases/{id}/search", json={"question": "一等座 批准"}
    ).json()
    assert found["strategy"] == "bm25" and found["hits"][0]["chunk"]["document_id"] == doc["id"]
    knowledge = api_client.app.state.knowledge
    reopened = KnowledgeService(knowledge.database, knowledge.files)
    actor = Actor(
        "user", "", library_owner(knowledge, id), "admin", "admin", utc_now() + timedelta(hours=1)
    )
    assert reopened.search(actor, id, SearchRequest(question="一等座")).hits
    assert (
        TestClient.request(
            api_client, "DELETE", f"/api/knowledge-bases/{id}/documents/{doc['id']}"
        ).status_code
        == 204
    )
    assert (
        api_client.post(f"/api/knowledge-bases/{id}/search", json={"question": "一等座"}).json()[
            "hits"
        ]
        == []
    )
    assert (
        api_client.get(f"/api/knowledge-bases/{id}/documents/{doc['id']}/original").status_code
        == 404
    )


def test_idempotency_content_duplicate_and_conflicting_retry(api_client):
    id = create(api_client)["id"]
    request_id = str(uuid4())
    first = upload(api_client, id, request_id=request_id).json()
    assert upload(api_client, id, request_id=request_id).json()["id"] == first["id"]
    assert upload(api_client, id, name="另一个名称.md").json()["id"] == first["id"]
    assert upload(api_client, id, data="不同内容", request_id=request_id).status_code == 409
    assert api_client.get(f"/api/knowledge-bases/{id}").json()["document_count"] == 1


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"\xff\xfe", "bad.md"),
        (b"", "empty.txt"),
        (b"%PDF-1", "test.pdf"),
        (b"a" * (128 * 1024 + 1), "large.md"),
        (b"a\x00b", "bad.txt"),
    ],
)
def test_rejected_upload_keeps_existing_documents(api_client, data, name):
    id = create(api_client)["id"]
    assert upload(api_client, id).status_code == 201
    assert upload(api_client, id, data=data, name=name).status_code == 422
    assert api_client.get(f"/api/knowledge-bases/{id}").json()["document_count"] == 1


def test_scope_and_query_escaping(api_client):
    first = create(api_client)["id"]
    other = create(api_client)["id"]
    doc = upload(api_client, first).json()
    assert api_client.get(f"/api/knowledge-bases/{other}/documents/{doc['id']}").status_code == 404
    assert (
        api_client.post(f"/api/knowledge-bases/{other}/search", json={"question": "一等座"}).json()[
            "hits"
        ]
        == []
    )
    assert (
        api_client.post(
            f"/api/knowledge-bases/{first}/search", json={"question": '" OR * NOT 一等座'}
        ).status_code
        == 200
    )
    service = api_client.app.state.knowledge
    stranger = Actor("user", "", str(uuid4()), "other", "admin", utc_now() + timedelta(hours=1))
    assert service.libraries(stranger) == []
    with pytest.raises(NotFoundError):
        service.get(stranger, first)


def test_retained_original_survives_attachment_sweep(api_client):
    kb = create(api_client)["id"]
    doc = upload(api_client, kb).json()
    service = api_client.app.state.knowledge
    with service.database.transaction() as session:
        row = session.get(LibraryDocument, doc["id"])
        file = session.get(StoredFile, row.file_id)
        file.created_at = utc_now() - timedelta(days=2)
    api_client.app.state.file_cleanup.sweep(retained_file_ids)
    assert (
        api_client.get(f"/api/knowledge-bases/{kb}/documents/{doc['id']}/original").status_code
        == 200
    )


def test_index_write_failure_rolls_back_document_and_chunks(api_client, monkeypatch):
    from sqlalchemy.orm import Session

    kb = create(api_client)["id"]
    upload(api_client, kb)
    process(api_client, kb)
    execute = Session.execute

    def reject_index(self, statement, *args, **kwargs):
        if "INSERT INTO knowledge_fts" in str(statement):
            raise RuntimeError("simulated index failure")
        return execute(self, statement, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "execute", reject_index)
        response = upload(api_client, kb, data="# 新资料\n不可部分入库。")
        assert response.status_code == 201
        result = process(api_client, kb).json()
        assert result["status"] == "failed"
        assert "simulated index failure" not in str(result)
    assert api_client.get(f"/api/knowledge-bases/{kb}").json()["document_count"] == 2
    with api_client.app.state.database.transaction() as session:
        assert session.execute(text("SELECT count(*) FROM knowledge_fts")).scalar() == 1
        assert len(list(session.scalars(select(LibraryDocument)))) == 2


def test_demo_import_uses_same_persistent_ingestion_and_is_repeatable(api_client):
    kb = create(api_client)["id"]
    data = {"preset": "technical", "client_request_id": str(uuid4())}
    response = api_client.post(f"/api/knowledge-bases/{kb}/demo-import", json=data)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 4
    assert len(api_client.post(f"/api/knowledge-bases/{kb}/demo-import", json=data).json()) == 4
    assert api_client.get(f"/api/knowledge-bases/{kb}").json()["document_count"] == 4
    process(api_client, kb)
    hits = api_client.post(
        f"/api/knowledge-bases/{kb}/search", json={"question": "发布回滚"}
    ).json()["hits"]
    assert hits and all(
        hit["chunk"]["document_id"] in {d["id"] for d in response.json()} for hit in hits
    )
    assert (
        api_client.post(
            f"/api/knowledge-bases/{kb}/demo-import", json={**data, "preset": "../../secrets"}
        ).status_code
        == 422
    )


def test_guest_is_rejected_before_any_library_access(api_client):
    actor = Actor("guest", "", None, None, "guest", utc_now() + timedelta(hours=1))
    from app.errors import PermissionDeniedError

    with pytest.raises(PermissionDeniedError):
        api_client.app.state.knowledge.libraries(actor)
