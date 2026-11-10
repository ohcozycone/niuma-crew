from contextlib import closing

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from app.knowledge.contracts import Chunk, RetrievalStrategy, TokenCount
from experiments.knowledge_poc.contracts import Candidate, RetrievalPreset, RetrievalResult
from experiments.knowledge_poc.indexing import Release, lexical_terms


def lexical_search(release: Release, question: str, k: int) -> tuple[Candidate, ...]:
    if k < 1:
        raise ValueError("candidate limit must be positive")
    terms = tuple(dict.fromkeys(lexical_terms(question)))[:64]
    if not terms:
        return ()
    expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
    with closing(release.connect_lexical()) as db:
        rows = db.execute(
            "SELECT chunk_id,bm25(chunks,2.0,1.0,0.0) AS score FROM chunks "
            "WHERE chunks MATCH ? ORDER BY score ASC,rowid ASC LIMIT ?",
            (expression, min(k, 100)),
        ).fetchall()
    return tuple(
        Candidate(chunk_id=id, rank=i, score=score, score_kind="fts5_bm25_lower_better")
        for i, (id, score) in enumerate(rows, 1)
    )


def vector_search(release: Release, question: str, k: int) -> tuple[Candidate, ...]:
    if not question.strip():
        return ()
    rows = release.store.similarity_search_with_score(question, k=min(k, len(release.chunks)))
    result = []
    for i, (doc, score) in enumerate(rows, 1):
        id = doc.metadata["chunk_id"]
        if id not in release.chunks or doc.metadata["release_id"] != release.manifest["release_id"]:
            raise ValueError("vector candidate outside release")
        result.append(
            Candidate(chunk_id=id, rank=i, score=score, score_kind="cosine_distance_lower_better")
        )
    return tuple(result)


def reciprocal_rank_fusion(
    lexical: tuple[Candidate, ...], vector: tuple[Candidate, ...], preset: RetrievalPreset
) -> tuple[Candidate, ...]:
    scores: dict[str, float] = {}
    for route, weight in ((lexical, preset.lexical_weight), (vector, preset.vector_weight)):
        seen = set()
        for item in route:
            if item.chunk_id not in seen:
                scores[item.chunk_id] = scores.get(item.chunk_id, 0) + weight / (
                    preset.rrf_c + item.rank
                )
                seen.add(item.chunk_id)
    return tuple(
        Candidate(chunk_id=id, rank=i, score=score, score_kind="rrf")
        for i, (id, score) in enumerate(sorted(scores.items(), key=lambda x: (-x[1], x[0])), 1)
    )


def evidence_text(index: int, chunk: Chunk) -> str:
    return f"[E{index}] {chunk.title} / {chunk.locator}\n{chunk.text}"


def retrieve(
    release: Release,
    question: str,
    strategy: RetrievalStrategy,
    preset: RetrievalPreset,
    count: TokenCount,
) -> RetrievalResult:
    """技术失败直接抛出；不会以空列表静默降级。"""
    if strategy not in {"bm25", "vector", "hybrid"}:
        raise ValueError("unknown retrieval strategy")
    if len(question) > 8000:
        raise ValueError("question exceeds POC budget")
    lexical = (
        lexical_search(release, question, preset.lexical_candidates) if strategy != "vector" else ()
    )
    vector = (
        vector_search(release, question, preset.vector_candidates) if strategy != "bm25" else ()
    )
    fused = reciprocal_rank_fusion(lexical, vector, preset)
    evidence: list[Chunk] = []
    excluded = {}
    for candidate in fused:
        chunk = release.chunks[candidate.chunk_id]
        if any(
            c.document_version == chunk.document_version
            and c.start <= chunk.start
            and c.end >= chunk.end
            for c in evidence
        ):
            excluded[chunk.id] = "covered_by_selected_range"
            continue
        if len(evidence) >= preset.final_top_k:
            excluded[chunk.id] = "top_k"
            continue
        proposed = "\n\n".join(evidence_text(i, c) for i, c in enumerate([*evidence, chunk], 1))
        if count(proposed) > preset.evidence_tokens:
            excluded[chunk.id] = "token_budget"
            continue
        evidence.append(chunk)
    return RetrievalResult(
        scope_id=release.manifest["scope_id"],
        release_id=release.manifest["release_id"],
        strategy=strategy,
        lexical=lexical,
        vector=vector,
        fused=fused,
        evidence=tuple(evidence),
        excluded=excluded,
    )


class KnowledgeRetriever(BaseRetriever):
    """LangChain 适配；范围由构造时绑定，不让模型提供库或路径。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    release: Release
    preset: RetrievalPreset
    count: TokenCount
    strategy: RetrievalStrategy = "hybrid"

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        result = retrieve(self.release, query, self.strategy, self.preset, self.count)
        return [
            Document(
                page_content=c.text,
                metadata={
                    "chunk_id": c.id,
                    "document_version": c.document_version,
                    "start": c.start,
                    "end": c.end,
                },
            )
            for c in result.evidence
        ]
