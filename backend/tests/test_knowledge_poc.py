import asyncio
import json
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

pytest.importorskip("langchain_chroma", reason="install --group knowledge-poc")
pytest.importorskip("langchain_text_splitters", reason="install --group knowledge-poc")

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.knowledge.chunking import split_document
from experiments.knowledge_poc import DATASET, FixtureEmbeddings
from experiments.knowledge_poc.answering import answer_question, validate_answer
from experiments.knowledge_poc.contracts import Candidate, RetrievalPreset
from experiments.knowledge_poc.evaluation import evaluate_retrieval, load_dataset, range_coverage
from experiments.knowledge_poc.indexing import (
    CheckedEmbeddings,
    Release,
    build_release,
    validate_sources,
)
from experiments.knowledge_poc.loading import KnowledgeLoader, load_document
from experiments.knowledge_poc.retrieval import KnowledgeRetriever, reciprocal_rank_fusion, retrieve


class CountingEmbeddings(FixtureEmbeddings):
    def __init__(self):
        self.document_calls, self.query_calls = 0, 0

    def embed_documents(self, texts):
        self.document_calls += 1
        return super().embed_documents(texts)

    def embed_query(self, text):
        self.query_calls += 1
        return super().embed_query(text)


@pytest.fixture
def indexed(tmp_path):
    path = tmp_path / "input.md"
    path.write_text("# 住宿\n每晚报销标准 450 元。\n\n# 交通\n高铁一等座需要特别批准。\n")
    doc = load_document(path, "doc-1")
    preset = RetrievalPreset(chunk_tokens=50, overlap_tokens=5)
    chunks = split_document(doc, preset, len)
    model = CountingEmbeddings()
    id = build_release(
        tmp_path,
        "alice",
        (doc,),
        chunks,
        model,
        space_id="test-v1",
        preset=preset,
        tokenizer="test-character-count",
        embedding_kind="fixture",
    )
    return tmp_path, id, model, preset


def open_index(indexed):
    root, id, model, preset = indexed
    return Release(root, "alice", id, model, "test-v1"), preset


def test_source_mapping_keeps_repeated_headings_emoji_and_newlines(tmp_path):
    path = tmp_path / "repeat.md"
    text = "# 相同标题\r\n住宿标准。🙂\r\n\r\n# 相同标题\r\n住宿标准。🙂\r\n"
    path.write_bytes(b"\xef\xbb\xbf" + text.encode())
    document = load_document(path, "repeat")
    assert document.text == text.replace("\r\n", "\n")
    chunks = split_document(document, RetrievalPreset(chunk_tokens=15, overlap_tokens=3), len)
    validate_sources((document,), chunks)
    assert len({c.id for c in chunks}) == len(chunks)
    repeated = [c for c in chunks if "住宿标准" in c.text]
    assert repeated[0].spans[0].block_id != repeated[-1].spans[0].block_id
    assert all(document.text[c.start : c.end] == c.text and len(c.text) <= 15 for c in chunks)
    path.write_text(document.text + "新标准。")
    assert load_document(path, "repeat").version != document.version


def test_markdown_code_heading_does_not_create_fake_section(tmp_path):
    path = tmp_path / "code.md"
    path.write_text("# 正文\n```python\n# 不是章节\nx = 1\n```\n\n# 结尾\n结束\n")
    document = load_document(path, "code")
    assert [b.locator for b in document.blocks] == ["正文", "结尾"]


def test_docx_body_and_table_remain_in_document_order(tmp_path):
    from docx import Document

    path = tmp_path / "sample.docx"
    document = Document()
    document.add_paragraph("前文🙂")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "名称", "金额"
    document.add_paragraph("后文")
    document.save(path)
    loaded = load_document(path, "word")
    assert loaded.text == "前文🙂\n\n名称\t金额\n\n后文\n\n"
    assert loaded.blocks[1].locator == "表格块 2"


def test_pdf_text_page_and_empty_scan_are_distinguished(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 100 Td (Knowledge sample) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)
    loaded = load_document(path, "pdf")
    assert "Knowledge sample" in loaded.text and loaded.blocks[0].locator == "第 1 页"
    blank = PdfWriter()
    blank.add_blank_page(width=300, height=200)
    blank.write(path)
    with pytest.raises(ValueError, match="empty extracted"):
        load_document(path, "scan")


def test_loader_budget_and_unsupported_type(tmp_path):
    path = tmp_path / "huge.txt"
    path.write_text("a" * 10)
    with pytest.raises(ValueError, match="file budget"):
        list(KnowledgeLoader(path, max_bytes=5).lazy_load())
    path = tmp_path / "x.html"
    path.write_text("<p>body</p>")
    with pytest.raises(ValueError, match="unsupported"):
        load_document(path, "x")


def test_real_indexes_reopen_without_reembedding_documents(indexed):
    root, id, model, preset = indexed
    calls = model.document_calls
    first = Release(root, "alice", id, model, "test-v1")
    result = retrieve(first, "高铁一等座", "hybrid", preset, len)
    assert result.lexical and result.vector and result.evidence
    assert any("特别批准" in c.text for c in result.evidence)
    second = Release(root, "alice", id, model, "test-v1")
    assert model.document_calls == calls
    assert [c.id for c in retrieve(second, "住宿", "bm25", preset, len).evidence]
    assert KnowledgeRetriever(release=second, preset=preset, count=len).invoke("住宿")


def test_new_process_reads_persisted_indexes_without_reembedding(indexed):
    root, id, _, _ = indexed
    code = """
import json,sys
from pathlib import Path
from experiments.knowledge_poc.indexing import Release
from experiments.knowledge_poc.retrieval import retrieve
from experiments.knowledge_poc.contracts import RetrievalPreset
from experiments.knowledge_poc import FixtureEmbeddings
class QueryOnly(FixtureEmbeddings):
    def embed_documents(self,texts):
        raise AssertionError('reopened index must not reembed documents')
release=Release(Path(sys.argv[1]),'alice',sys.argv[2],QueryOnly(),'test-v1')
result=retrieve(release,'住宿','hybrid',RetrievalPreset(),len)
print(json.dumps({'evidence':len(result.evidence),'vector':len(result.vector)}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(root), id],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    data = json.loads(result.stdout)
    assert data["evidence"] > 0 and data["vector"] > 0


def test_scope_space_and_artifact_corruption_are_rejected(indexed):
    root, id, model, _ = indexed
    with pytest.raises(FileNotFoundError):
        Release(root, "bob", id, model, "test-v1")
    with pytest.raises(ValueError, match="space mismatch"):
        Release(root, "alice", id, model, "other")
    with pytest.raises(ValueError, match="invalid scope"):
        Release(root, "../alice", id, model, "test-v1")
    path = root / "releases/alice" / id / "chunks.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="hash mismatch"):
        Release(root, "alice", id, model, "test-v1")


def test_changed_lexical_tokenizer_is_rejected(indexed):
    root, id, model, _ = indexed
    path = root / "releases/alice" / id / "manifest.json"
    data = json.loads(path.read_text())
    data["lexical_version"] = "different-dictionary"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="lexical tokenizer version mismatch"):
        Release(root, "alice", id, model, "test-v1")


def test_missing_vector_collection_is_not_recreated(indexed):
    release, _ = open_index(indexed)
    name = release.manifest["collection"]
    release.store.delete_collection()
    with pytest.raises(Exception, match="[Cc]ollection|[Ee]xist"):
        open_index(indexed)
    from chromadb import PersistentClient
    from chromadb.config import Settings

    assert name not in [
        c.name
        for c in PersistentClient(
            path=str(indexed[0] / "chroma"), settings=Settings(anonymized_telemetry=False)
        ).list_collections()
    ]


def test_cancelled_new_build_keeps_old_release_and_cleans_staging(indexed):
    old, preset = open_index(indexed)
    root, _, model, _ = indexed
    calls = 0

    def guard():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise InterruptedError("cancelled")

    with pytest.raises(InterruptedError):
        build_release(
            root,
            "alice",
            old.documents,
            tuple(old.chunks.values()),
            model,
            space_id="test-v1",
            preset=preset,
            tokenizer="test",
            guard=guard,
        )
    assert not list((root / ".building").iterdir())
    assert retrieve(open_index(indexed)[0], "住宿", "bm25", preset, len).evidence


def test_invalid_vectors_cannot_be_indexed():
    checked = CheckedEmbeddings(FixtureEmbeddings(), dimension=2)
    with pytest.raises(ValueError, match="dimension"):
        checked.embed_query("test")
    with pytest.raises(ValueError, match="count"):
        checked._check([], 1)
    with pytest.raises(ValueError, match="non-finite"):
        checked._check([[float("nan"), 1]], 1)


def test_rrf_deduplicates_ids_and_breaks_ties_stably():
    def item(id, rank):
        return Candidate(chunk_id=id, rank=rank, score=1, score_kind="rrf")

    fused = reciprocal_rank_fusion(
        (item("x", 1), item("x", 2)), (item("y", 1), item("x", 3)), RetrievalPreset()
    )
    assert [x.chunk_id for x in fused] == ["x", "y"]
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 63)
    assert [
        x.chunk_id
        for x in reciprocal_rank_fusion((item("b", 1),), (item("a", 1),), RetrievalPreset())
    ] == ["a", "b"]


def test_empty_query_and_token_budget_do_not_create_fake_evidence(indexed):
    release, preset = open_index(indexed)
    assert not retrieve(release, "  ", "hybrid", preset, len).evidence
    limited = preset.model_copy(update={"evidence_tokens": 1})
    result = retrieve(release, "住宿", "bm25", limited, len)
    assert not result.evidence and "token_budget" in result.excluded.values()
    assert not retrieve(release, "zzzznolexicalmatch", "bm25", preset, len).evidence


def test_answer_uses_actual_context_and_rejects_unknown_citation(indexed):
    release, preset = open_index(indexed)
    result = retrieve(release, "住宿", "bm25", preset, len)
    valid = json.dumps(
        {"status": "answered", "sections": [{"text": "按晚计算。", "evidence_ids": ["E1"]}]}
    )
    answer, diagnostic = asyncio.run(
        answer_question(FakeListChatModel(responses=[valid]), "住宿", result)
    )
    assert answer.status == "answered" and diagnostic["model_called"]
    with pytest.raises(ValueError, match="outside actual context"):
        validate_answer(valid.replace("E1", "E999"), result)
    empty = retrieve(release, "zzzznolexicalmatch", "bm25", preset, len)
    _, diagnostic = asyncio.run(answer_question(FakeListChatModel(responses=[]), "x", empty))
    assert diagnostic["model_called"] is False


def test_coverage_uses_union_not_duplicate_hit_count(indexed):
    release, _ = open_index(indexed)
    chunk = next(iter(release.chunks.values()))
    ranges = [(chunk.document_version, chunk.start, chunk.end)]
    assert range_coverage((chunk, chunk), ranges) == {"covered": 1, "total": 1, "value": 1.0}
    assert range_coverage((), ranges)["value"] == 0
    assert range_coverage((), [])["value"] is None


def test_scoring_material_is_not_indexed_and_fixture_quality_is_blocked(indexed, tmp_path):
    docs = load_dataset(DATASET)
    assert len(docs) == 5
    release, preset = open_index(indexed)
    with pytest.raises(ValueError, match="cannot produce semantic quality"):
        evaluate_retrieval(release, DATASET, "hybrid", preset, len)
    (tmp_path / "documents").mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {"documents": [{"path": "../secret.txt", "doc_id": "x", "title": "x", "sha256": "x"}]}
        )
    )
    with pytest.raises(ValueError, match="outside documents"):
        load_dataset(tmp_path)


def test_failed_generation_keeps_planned_denominator_and_raw_output(indexed, monkeypatch):
    from experiments import knowledge_poc

    release, preset = open_index(indexed)
    result = retrieve(release, "住宿", "bm25", preset, len)
    rows = [
        {"question": "住宿", "status": "retrieved", "retrieval": result.model_dump()}
        for _ in range(2)
    ]
    rows.append({"question": "失败问题", "status": "retrieval_failed"})
    valid = '{"status":"insufficient","sections":[{"text":"资料不足","evidence_ids":[]}]}'

    @asynccontextmanager
    async def session(*args, **kwargs):
        yield FakeListChatModel(responses=["not-json", valid])

    monkeypatch.setattr(knowledge_poc, "chat_config", lambda _: None)
    monkeypatch.setattr(knowledge_poc, "model_session", session)
    path = indexed[0] / "progress.json"
    asyncio.run(knowledge_poc.generate_answers(rows, "test-connection", path))
    saved = json.loads(path.read_text())
    assert saved["planned_count"] == 3
    assert [r["status"] for r in saved["results"]] == [
        "generation_failed",
        "answered",
        "retrieval_failed",
    ]
    assert saved["results"][0]["generation"] == {"raw": "not-json", "usage": None}


def test_embedding_input_limit_rejects_before_external_call():
    from experiments.knowledge_poc import BoundedEmbeddings

    model = CountingEmbeddings()
    bounded = BoundedEmbeddings(model, len, 3)
    with pytest.raises(ValueError, match="token limit"):
        bounded.embed_documents(["超出长度"])
    assert model.document_calls == 0
