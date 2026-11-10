from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from app.knowledge.contracts import Chunk, FrozenModel, RetrievalStrategy


class RetrievalPreset(FrozenModel):
    chunk_tokens: int = Field(default=400, ge=8)
    overlap_tokens: int = Field(default=60, ge=0)
    lexical_candidates: int = Field(default=20, ge=1, le=100)
    vector_candidates: int = Field(default=20, ge=1, le=100)
    final_top_k: int = Field(default=6, ge=1, le=100)
    evidence_tokens: int = Field(default=3000, ge=1)
    rrf_c: int = Field(default=60, ge=1)
    lexical_weight: float = Field(default=1, gt=0, allow_inf_nan=False)
    vector_weight: float = Field(default=1, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_overlap(self) -> Self:
        if self.overlap_tokens >= self.chunk_tokens:
            raise ValueError("overlap must be smaller than chunk budget")
        return self


class Candidate(FrozenModel):
    chunk_id: str
    rank: int = Field(ge=1)
    score: float = Field(allow_inf_nan=False)
    score_kind: Literal["fts5_bm25_lower_better", "cosine_distance_lower_better", "rrf"]


class RetrievalResult(FrozenModel):
    scope_id: str
    release_id: str
    strategy: RetrievalStrategy
    lexical: tuple[Candidate, ...]
    vector: tuple[Candidate, ...]
    fused: tuple[Candidate, ...]
    evidence: tuple[Chunk, ...]
    excluded: dict[str, str]


class AnswerSection(FrozenModel):
    text: str = Field(min_length=1)
    evidence_ids: tuple[str, ...]


class KnowledgeAnswer(FrozenModel):
    status: Literal["answered", "partial", "insufficient", "conflict"]
    sections: tuple[AnswerSection, ...]
