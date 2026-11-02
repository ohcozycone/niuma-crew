"""公开开发题的原文覆盖诊断；评分材料只进入评分阶段。"""

import json
from collections import defaultdict
from pathlib import Path

from app.knowledge.contracts import (
    Chunk,
    KnowledgeDocument,
    RetrievalPreset,
    RetrievalStrategy,
    TokenCount,
)
from app.knowledge.indexing import Release
from app.knowledge.loading import load_document, normalize
from app.knowledge.retrieval import retrieve


def load_dataset(directory: Path) -> tuple[KnowledgeDocument, ...]:
    """只加载清单 documents/ 条目，拒绝目录穿越与题目泄漏。"""
    manifest = json.loads((directory / "manifest.json").read_text())
    root = (directory / "documents").resolve()
    documents = []
    for item in manifest["documents"]:
        path = (directory / item["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("dataset document outside documents directory")
        document = load_document(path, item["doc_id"], item["title"])
        if document.original_sha256 != item["sha256"]:
            raise ValueError("dataset source hash mismatch")
        documents.append(document)
    return tuple(documents)


def quote_ranges(release: Release, reference: dict) -> list[tuple[str, int, int]]:
    documents = {d.id: d for d in release.documents}
    ranges = []
    for evidence in reference["evidence"]:
        document = documents[evidence["doc_id"]]
        quote = normalize(evidence["quote"])
        positions = []
        cursor = 0
        while (position := document.text.find(quote, cursor)) >= 0:
            positions.append(position)
            cursor = position + 1
        if len(positions) != 1:
            raise ValueError("reference quote missing or ambiguous; manual review required")
        ranges.append((document.version, positions[0], positions[0] + len(quote)))
    return ranges


def range_coverage(chunks: tuple[Chunk, ...], ranges: list[tuple[str, int, int]]) -> dict:
    """以原文区间并集计完整引文覆盖，重叠命中不重复计数。"""
    intervals: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for chunk in chunks:
        intervals[chunk.document_version].append((chunk.start, chunk.end))
    hits = 0
    for version, start, end in ranges:
        cursor = start
        for a, b in sorted(intervals[version]):
            if a > cursor:
                break
            if b > cursor:
                cursor = b
            if cursor >= end:
                hits += 1
                break
    return {"covered": hits, "total": len(ranges), "value": hits / len(ranges) if ranges else None}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def evaluate_retrieval(
    release: Release,
    directory: Path,
    strategy: RetrievalStrategy,
    preset: RetrievalPreset,
    count: TokenCount,
) -> list[dict]:
    """返回真实检索轨迹和开发引文覆盖；不自动宣告答案正确。"""
    if strategy != "bm25" and release.manifest["embedding_kind"] != "semantic_api":
        raise ValueError("fixture embeddings cannot produce semantic quality evaluation")
    questions = read_jsonl(directory / "evaluation/questions.jsonl")
    references = {r["id"]: r for r in read_jsonl(directory / "evaluation/reference_answers.jsonl")}
    rows = []
    for question in questions:
        row = {
            "case_id": question["id"],
            "question": question["question"],
            "strategy": strategy,
            "status": "retrieval_failed",
            "review_status": "pending",
        }
        try:
            # 参考答案不传给 retrieve 或生成器；先完成实际检索，后解析评分引文。
            result = retrieve(release, question["question"], strategy, preset, count)
            reference = references[question["id"]]
            ranges = quote_ranges(release, reference)
            candidates = tuple(release.chunks[c.chunk_id] for c in result.fused)
            row.update(
                {
                    "status": "retrieved",
                    "reference_quote_coverage_candidates": range_coverage(candidates, ranges),
                    "reference_quote_coverage_context": range_coverage(result.evidence, ranges),
                    "retrieval": result.model_dump(mode="json"),
                }
            )
        except Exception as error:
            row["error_type"] = type(error).__name__
        rows.append(row)
    return rows
