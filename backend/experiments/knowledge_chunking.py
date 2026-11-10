import json
import sqlite3
from pathlib import Path

from app.knowledge.chunking import split_document
from app.knowledge.contracts import Chunk, KnowledgeDocument
from app.knowledge.lexical import lexical_terms, lexical_version
from app.knowledge.loading import text_document
from app.knowledge.samples import DATASET, sample_files
from experiments.knowledge_poc.contracts import RetrievalPreset

FAQ = Path(__file__).resolve().parents[1] / "datasets/knowledge-chunking/faq.md"


def documents() -> tuple[KnowledgeDocument, ...]:
    """仅加载公开合成原件，题目和答案不进入索引。"""
    manifest = json.loads((DATASET / "manifest.json").read_text())
    ids = {Path(item["path"]).name: item["doc_id"] for item in manifest["documents"]}
    return tuple(
        text_document(data, ids.get(name, name), name)
        for name, data in sample_files("travel")
        + sample_files("technical")
        + [(FAQ.name, FAQ.read_bytes())]
    )


def covered(chunks: list[Chunk], document: KnowledgeDocument, quote: str) -> bool:
    """按原文区间计算完整覆盖，重叠部分只计一次。"""
    assert document.text.count(quote) == 1, "missing or ambiguous scoring quote"
    cursor = document.text.index(quote)
    end = cursor + len(quote)
    for chunk in sorted((c for c in chunks if c.document_id == document.id), key=lambda c: c.start):
        if chunk.start > cursor:
            break
        cursor = max(cursor, chunk.end)
        if cursor >= end:
            return True
    return False


def compare(minimum: int, sources: tuple[KnowledgeDocument, ...]) -> dict:
    chunks = tuple(
        c
        for document in sources
        for c in split_document(
            document,
            RetrievalPreset(chunk_tokens=800, overlap_tokens=120),
            len,
            min_section_chars=minimum,
            max_chunks=5000,
        )
    )
    by_id = {c.id: c for c in chunks}
    source_by_id = {d.id: d for d in sources}
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE VIRTUAL TABLE chunks USING fts5(id UNINDEXED, content)")
        db.executemany(
            "INSERT INTO chunks VALUES (?, ?)",
            ((c.id, " ".join(lexical_terms(c.index_text))) for c in chunks),
        )
        # 索引全部写入后才加载评分依据，避免泄漏答案。
        references = [
            json.loads(line)
            for line in (DATASET / "evaluation/reference_answers.jsonl").read_text().splitlines()
        ]
        for question, doc, quote in (
            (
                "发布连续三分钟健康检查失败如何回滚",
                "发布与回滚.md",
                "新版本连续三分钟无法通过健康检查，或关键请求错误率超过百分之二时，停止扩大发布。",
            ),
            (
                "网络中断后重试创建资源需要保留什么",
                "API错误处理.md",
                "网络中断不等于服务端没有执行。",
            ),
            (
                "发票丢失怎么办，行程证明需要哪些内容",
                "faq.md",
                "行程证明应包含实际出发和到达日期、出发地和目的地，并能对应已批准的出差申请及所报交通费用。",
            ),
            (
                "超标住宿是否需要特别批准，提交报销后多久到账",
                "faq.md",
                "普通出差批准不能代替超标住宿批准。",
            ),
        ):
            references.append(
                {
                    "id": f"extra-{len(references)}",
                    "question": question,
                    "evidence": [{"doc_id": doc, "quote": quote}],
                }
            )
        scores = []
        for case in references:
            terms = tuple(dict.fromkeys(lexical_terms(case["question"])))[:64]
            query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
            hits = [
                by_id[row[0]]
                for row in db.execute(
                    "SELECT id FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks), id LIMIT 6",
                    (query,),
                )
            ]
            expected = case["evidence"]
            scores.append(
                {
                    "id": case["id"],
                    "covered": sum(
                        covered(hits, source_by_id[e["doc_id"]], e["quote"]) for e in expected
                    ),
                    "expected": len(expected),
                }
            )
    return {
        "minimum": minimum,
        "chunks": len(chunks),
        "under_200": sum(len(c.text) < 200 for c in chunks),
        "merged": sum(len(c.spans) > 1 for c in chunks),
        "max_length": max(len(c.text) for c in chunks),
        "covered_evidence": sum(s["covered"] for s in scores),
        "expected_evidence": sum(s["expected"] for s in scores),
        "cases": scores,
    }


if __name__ == "__main__":
    sources = documents()
    print(
        json.dumps(
            {
                "documents": len(sources),
                "lexical_version": lexical_version(),
                "results": [compare(n, sources) for n in (0, 100, 200, 300)],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
