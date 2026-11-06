"""知识原文、切片和检索结果；不依赖业务数据库或 SDK 消息。"""

from collections.abc import Callable
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

TOOL_BINDINGS = {"search_knowledge": "knowledge:search", "read_knowledge_source": "knowledge:read"}

TokenCount = Callable[[str], int]
Guard = Callable[[], None]
RetrievalStrategy = Literal["bm25", "vector", "hybrid"]


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


class ChunkingRules(FrozenModel):
    chunk_tokens: int = Field(default=400, ge=8)
    overlap_tokens: int = Field(default=60, ge=0)

    @model_validator(mode="after")
    def validate_overlap(self) -> Self:
        if self.overlap_tokens >= self.chunk_tokens:
            raise ValueError("overlap must be smaller than chunk budget")
        return self
