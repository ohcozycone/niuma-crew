"""Fuse trusted candidate rankings with LangChain's public RRF implementation."""

from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from app.knowledge.schemas import SearchHit


def fuse_rankings(rankings: list[list[SearchHit]], top_k: int) -> list[SearchHit]:
    """Return rank-only results; raw scores from different retrievers are incomparable."""
    candidates = {hit.chunk.id: hit.chunk for ranking in rankings for hit in ranking}
    if not candidates:
        return []

    def stream(ranking: list[SearchHit]) -> RunnableLambda:
        documents = [
            Document(page_content=hit.chunk.text, metadata={"chunk_id": hit.chunk.id})
            for hit in ranking
        ]
        return RunnableLambda(lambda _query: documents)

    retriever = EnsembleRetriever(
        retrievers=[stream(ranking) for ranking in rankings],
        weights=[1 / len(rankings)] * len(rankings),
        c=60,
        id_key="chunk_id",
    )
    return [
        SearchHit(
            rank=rank,
            score=None,
            score_kind="rank_only",
            chunk=candidates[doc.metadata["chunk_id"]],
        )
        for rank, doc in enumerate(retriever.invoke("")[:top_k], 1)
    ]
