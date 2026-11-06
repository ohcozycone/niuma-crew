"""Section-aware chunks retain evidence, and preview matches durable publication."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_knowledge_library import create, process, upload

from app.auth.actor import Actor
from app.errors import NotFoundError
from app.knowledge.chunking import ChunkLimitExceeded, split_document
from app.knowledge.contracts import ChunkingRules
from app.knowledge.loading import text_document
from app.knowledge.models import KnowledgeBase, LibraryChunk, ProcessingBatch
from app.knowledge.schemas import ChunkPreviewRequest
from app.values import utc_now

BODY = "# 报销流程\n总则\n\n## 提交申请\n先提交出差申请。\n\n## 准备凭证\n准备发票和住宿明细。\n\n## 审批\n交给主管审批。\n"
RULES = {"chunk_size": 300, "chunk_overlap": 20, "min_section_chars": 80}


def detail(client, kb, doc):
    return client.get(f"/api/knowledge-bases/{kb}/documents/{doc}").json()


def split(body=BODY, minimum=80, size=300, overlap=20):
    document = text_document(body.encode(), "doc", "流程.md")
    chunks = split_document(
        document,
        ChunkingRules(chunk_tokens=size, overlap_tokens=overlap),
        len,
        min_section_chars=minimum,
    )
    return document, chunks


def test_short_siblings_keep_all_source_spans_and_original_text():
    document, chunks = split()
    assert len(chunks) == 2
    merged = chunks[1]
    assert len(merged.spans) == 3
    assert all(label in merged.locator for label in ("报销流程 / 提交申请", "准备凭证", "审批"))
    assert "".join(c.text for c in chunks) == document.text
    by_id = {b.id: b for b in document.blocks}
    for chunk in chunks:
        assert chunk.text == document.text[chunk.start : chunk.end]
        assert (
            "".join(
                document.text[by_id[s.block_id].start + s.start : by_id[s.block_id].start + s.end]
                for s in chunk.spans
            )
            == chunk.text
        )


def test_repeated_parent_names_and_top_level_topics_never_merge():
    body = "# 同名\n## 一\n甲\n## 二\n乙\n# 同名\n## 一\n丙\n## 二\n丁\n"
    document, chunks = split(body)
    assert len(chunks) == 4
    assert document.blocks[1].parent_id != document.blocks[4].parent_id
    assert all(not ("甲" in c.text and "丙" in c.text) for c in chunks)
    assert len(split("# 一\n甲\n# 二\n乙\n")[1]) == 2


def test_long_section_is_not_absorbed_and_fenced_headings_are_not_sections():
    body = (
        "# 手册\n## 短一\n甲\n## 长节\n"
        + "正文。" * 100
        + "\n## 短二\n乙\n## 示例\n```md\n# 伪标题\n```\n"
    )
    document, chunks = split(body, size=100, overlap=10)
    assert len(document.blocks) == 5
    assert all(not ("短一" in c.text and "长节" in c.text) for c in chunks)
    assert all(len(c.text) <= 100 for c in chunks)
    cursor, recovered = 0, ""
    for chunk in chunks:
        assert chunk.start <= cursor and chunk.end > cursor
        recovered += document.text[cursor : chunk.end]
        cursor = chunk.end
    assert recovered == document.text


def test_disabled_merging_and_allocation_budget():
    assert len(split(minimum=0)[1]) == 4
    document = split()[0]
    with pytest.raises(ChunkLimitExceeded):
        split_document(
            document, ChunkingRules(chunk_tokens=100, overlap_tokens=10), len, max_chunks=1
        )


def test_preview_has_no_publication_and_explicit_rules_match_background_result(api_client):
    kb = create(api_client)["id"]
    doc = upload(api_client, kb, BODY).json()
    url = f"/api/knowledge-bases/{kb}/documents/{doc['id']}/preview"
    response = api_client.post(url, json={"rules": RULES})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["merged_chunk_count"] == 1 and preview["chunk_count"] == 2
    assert detail(api_client, kb, doc["id"])["document"] is None
    with api_client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(LibraryChunk)) == 0
        assert db.scalar(select(func.count()).select_from(ProcessingBatch)) == 0
    job = api_client.post(
        f"/api/knowledge-bases/{kb}/processing",
        json={
            "client_request_id": str(uuid4()),
            "document_ids": [doc["id"]],
            "rules": RULES,
        },
    )
    assert job.status_code == 202
    api_client.app.state.knowledge.processing.run_next()
    actual = detail(api_client, kb, doc["id"])
    assert actual["chunks"] == preview["chunks"]
    assert actual["processing_rules"] == {**RULES, "split_version": 2}
    assert api_client.get(f"/api/knowledge-bases/{kb}").json()["chunk_size"] is None


def test_preview_pages_all_chunks_without_truncating_counts(api_client):
    kb = create(api_client)["id"]
    doc = upload(api_client, kb, "".join(f"# 主题{i}\n资料{i}\n" for i in range(25))).json()
    url = f"/api/knowledge-bases/{kb}/documents/{doc['id']}/preview"
    first = api_client.post(url, json={}).json()
    second = api_client.post(url, json={"offset": 20}).json()
    assert first["chunk_count"] == 25 and len(first["chunks"]) == 20 and first["has_more"]
    assert len(second["chunks"]) == 5 and not second["has_more"]
    assert set(c["id"] for c in first["chunks"]).isdisjoint(c["id"] for c in second["chunks"])


def test_preview_rejects_excessive_fragmentation_without_publishing(api_client):
    kb = create(api_client)["id"]
    doc = upload(api_client, kb, "# 长文\n" + "甲" * 6000).json()
    url = f"/api/knowledge-bases/{kb}/documents/{doc['id']}/preview"
    result = api_client.post(
        url, json={"rules": {"chunk_size": 100, "chunk_overlap": 99, "min_section_chars": 0}}
    )
    assert (
        result.status_code == 422
        and result.json()["detail"]["code"] == "knowledge_chunk_quota_exceeded"
    )
    assert detail(api_client, kb, doc["id"])["document"] is None


def test_invalid_rules_scope_and_deletion_during_preview(api_client, monkeypatch):
    base = create(api_client)
    kb = base["id"]
    doc = upload(api_client, kb, BODY).json()
    url = f"/api/knowledge-bases/{kb}/documents/{doc['id']}/preview"
    invalid = {**RULES, "min_section_chars": 300}
    assert api_client.post(url, json={"rules": invalid}).status_code == 422
    assert (
        api_client.post(
            f"/api/knowledge-bases/{kb}/processing",
            json={"client_request_id": str(uuid4()), "rules": invalid},
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            f"/api/knowledge-bases/{str(uuid4())}/documents/{doc['id']}/preview", json={}
        ).status_code
        == 404
    )
    service = api_client.app.state.knowledge
    stranger = Actor("user", "", str(uuid4()), "other", "admin", utc_now() + timedelta(hours=1))
    with pytest.raises(NotFoundError):
        service.processing.preview(stranger, kb, doc["id"], ChunkPreviewRequest())
    with service.database.transaction() as db:
        owner_id = db.get(KnowledgeBase, kb).owner_user_id
    owner = Actor("user", "", owner_id, "admin", "admin", utc_now() + timedelta(hours=1))
    native = service.processing.prepare

    def prepare(*args):
        result = native(*args)
        service.remove(owner, kb, doc["id"])
        return result

    monkeypatch.setattr(service.processing, "prepare", prepare)
    assert api_client.post(url, json={}).status_code == 404


def test_legacy_queued_rules_do_not_silently_enable_merging(api_client):
    kb = create(api_client)["id"]
    doc = upload(api_client, kb, BODY).json()
    job = process(api_client, kb, run=False).json()
    with api_client.app.state.database.transaction() as db:
        db.get(ProcessingBatch, job["id"]).rules = {"chunk_size": 800, "chunk_overlap": 120}
    api_client.app.state.knowledge.processing.run_next()
    assert len(detail(api_client, kb, doc["id"])["chunks"]) == 4
