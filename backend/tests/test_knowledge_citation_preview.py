"""Citation cards read one current authorized fragment, never an entire source document."""

from datetime import timedelta

import pytest
from test_knowledge_library import create, process, upload

from app.auth.actor import Actor
from app.errors import NotFoundError
from app.knowledge.models import KnowledgeBase, LibraryChunk
from app.values import utc_now


def fixture(client):
    base = create(client)
    document = upload(
        client, base["id"], "# 报销制度\n## 发票\n" + "缺票时联系开票方补发，并提供情况说明。" * 100
    ).json()
    process(client, base["id"])
    detail = client.get(f"/api/knowledge-bases/{base['id']}/documents/{document['id']}").json()
    chunk = max(detail["chunks"], key=lambda value: len(value["text"]))
    return base, document, chunk


def test_citation_preview_is_bounded_and_matches_exact_source(api_client):
    base, document, chunk = fixture(api_client)
    assert len(chunk["text"]) > 600
    response = api_client.get(
        f"/api/knowledge-bases/{base['id']}/documents/{document['id']}/chunks/{chunk['id']}"
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["excerpt"] == chunk["text"][:600]
    assert result["has_more"] is True
    assert result["locator"] == chunk["locator"]
    assert (
        result["source_url"]
        == f"/knowledge/{base['id']}/documents/{document['id']}?chunk={chunk['id']}"
    )
    assert "chunks" not in result and "document" not in result
    with api_client.app.state.knowledge.database.transaction() as db:
        row = db.get(LibraryChunk, chunk["id"])
        row.snapshot = {**row.snapshot, "title": "标题" * 300, "locator": "章节" * 600}
    bounded = api_client.get(
        f"/api/knowledge-bases/{base['id']}/documents/{document['id']}/chunks/{chunk['id']}"
    ).json()
    assert len(bounded["title"]) == 300
    assert len(bounded["locator"]) == 600


def test_citation_preview_rejects_mismatched_document_and_library(api_client):
    base, document, chunk = fixture(api_client)
    another = upload(api_client, base["id"], "# 另一文档\n其他正文", "其他.md").json()
    other_base = create(api_client, "其他库")
    for kb, doc in ((base["id"], another["id"]), (other_base["id"], document["id"])):
        assert (
            api_client.get(
                f"/api/knowledge-bases/{kb}/documents/{doc}/chunks/{chunk['id']}"
            ).status_code
            == 404
        )
    assert (
        api_client.get(
            f"/api/knowledge-bases/{base['id']}/documents/{document['id']}/chunks/not-a-chunk"
        ).status_code
        == 422
    )


def test_citation_preview_checks_owner_and_current_fragment(api_client):
    base, document, chunk = fixture(api_client)
    service = api_client.app.state.knowledge
    with service.database.transaction() as db:
        owner = db.get(KnowledgeBase, base["id"]).owner_user_id
    other = Actor(
        "user",
        "",
        "00000000-0000-0000-0000-000000000000",
        "other",
        "admin",
        utc_now() + timedelta(hours=1),
    )
    with pytest.raises(NotFoundError):
        service.citation_preview(other, base["id"], document["id"], chunk["id"])
    with service.database.transaction() as db:
        row = db.get(LibraryChunk, chunk["id"])
        row.snapshot = {**row.snapshot, "document_version": "changed"}
    assert (
        api_client.get(
            f"/api/knowledge-bases/{base['id']}/documents/{document['id']}/chunks/{chunk['id']}"
        ).status_code
        == 404
    )
    actor = Actor("user", "", owner, "owner", "admin", utc_now() + timedelta(hours=1))
    service.remove(actor, base["id"], document["id"])
    assert (
        api_client.get(
            f"/api/knowledge-bases/{base['id']}/documents/{document['id']}/chunks/{chunk['id']}"
        ).status_code
        == 404
    )
