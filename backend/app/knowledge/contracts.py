"""知识原文、切片和检索结果；不依赖业务数据库或 SDK 消息。"""

import hashlib
import json
from collections.abc import Callable
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

TokenCount = Callable[[str], int]
Guard = Callable[[], None]
RetrievalStrategy = Literal["bm25", "vector", "hybrid"]


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceBlock(FrozenModel):
    id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    locator: str
    parent_id: str | None = None
    heading_path: tuple[str, ...] = ()


class KnowledgeDocument(FrozenModel):
    id: str
    version: str
    title: str
    text: str = Field(min_length=1)
    blocks: tuple[SourceBlock, ...]
    original_sha256: str
    parser: str
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_blocks(self) -> Self:
        cursor = 0
        for block in self.blocks:
            if block.start != cursor or not block.start < block.end <= len(self.text):
                raise ValueError("source blocks must partition canonical text")
            cursor = block.end
        if cursor != len(self.text) or len({b.id for b in self.blocks}) != len(self.blocks):
            raise ValueError("source blocks must be complete and unique")
        return self


class SourceSpan(FrozenModel):
    block_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class Chunk(FrozenModel):
    id: str
    document_id: str
    document_version: str
    title: str
    locator: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    spans: tuple[SourceSpan, ...]
    text: str = Field(min_length=1)
    index_text: str = Field(min_length=1)


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
