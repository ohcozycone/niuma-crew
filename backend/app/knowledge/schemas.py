"""HTTP shapes for libraries, originals and explicit BM25 diagnostics."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.knowledge.contracts import Chunk, KnowledgeDocument
from app.schemas import NonBlankText, RequestModel

ProcessingState = Literal["pending", "queued", "processing", "ready", "failed", "interrupted"]


class ChunkingRules(RequestModel):
    chunk_size: int = Field(ge=100, le=2000)
    chunk_overlap: int = Field(ge=0, le=1000)
    min_section_chars: int = Field(ge=0, le=2000)

    @model_validator(mode="after")
    def validate_lengths(self) -> Self:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("重叠字符数必须小于切分字符数。")
        if self.min_section_chars > self.chunk_size - self.chunk_overlap:
            raise ValueError("短章节阈值不能超过切分字符数减去重叠字符数。")
        return self


def effective_rules(size: int | None, overlap: int | None, minimum: int | None) -> ChunkingRules:
    """Resolve inherited defaults once for settings, preview and durable submission."""
    size, overlap = size or 800, 120 if overlap is None else overlap
    return ChunkingRules(
        chunk_size=size,
        chunk_overlap=overlap,
        min_section_chars=min(200, size - overlap) if minimum is None else minimum,
    )


class LibraryCreate(RequestModel):
    name: Annotated[NonBlankText, Field(max_length=100)]
    description: str = Field(default="", max_length=1000)
    client_request_id: UUID


class LibraryRead(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    chunk_count: int
    updated_at: datetime
    search_mode: Literal["bm25"] = "bm25"
    vector_status: Literal["not_built", "ready", "partial", "outdated", "unavailable"] = "not_built"
    vector_connection_id: str | None = None
    vector_connection_name: str | None = None
    vector_chunk_count: int = 0
    revision: int = 1
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    min_section_chars: int | None = None
    effective_chunk_size: int = 800
    effective_chunk_overlap: int = 120
    effective_min_section_chars: int = 200
    keyword_document_count: int = 0
    processing_document_count: int = 0


class LibraryUpdate(RequestModel):
    expected_revision: int = Field(ge=1)
    name: Annotated[NonBlankText, Field(max_length=100)]
    description: str = Field(max_length=1000)
    chunk_size: int | None = Field(default=None, ge=100, le=2000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=1000)
    min_section_chars: int | None = Field(default=None, ge=0, le=2000)


class DocumentRead(BaseModel):
    id: str
    title: str
    filename: str
    size: int
    content_hash: str
    version: str
    chunk_count: int
    created_at: datetime
    processing_state: ProcessingState = "ready"
    processing_error: str | None = None
    keyword_ready: bool = True
    vector_ready: bool = False
    processing_rules: dict = {}


class DocumentDetail(DocumentRead):
    document: KnowledgeDocument | None
    chunks: list[Chunk]


class CitationPreviewRead(BaseModel):
    title: str = Field(max_length=300)
    locator: str = Field(max_length=600)
    excerpt: str = Field(max_length=600)
    has_more: bool
    source_url: str


class ProcessingRequest(RequestModel):
    client_request_id: UUID
    document_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=200)
    reprocess: bool = False
    rules: ChunkingRules | None = None


class ChunkPreviewRequest(RequestModel):
    rules: ChunkingRules | None = None
    offset: int = Field(default=0, ge=0, le=5000)


class ChunkPreviewRead(BaseModel):
    document_id: str
    filename: str
    rules: ChunkingRules
    chunk_count: int
    short_chunk_count: int
    merged_chunk_count: int
    min_length: int
    max_length: int
    offset: int
    has_more: bool
    chunks: list[Chunk]


class ProcessingItemRead(BaseModel):
    id: str
    document_id: str
    filename: str
    status: str
    error: str | None


class ProcessingBatchRead(BaseModel):
    id: str
    status: str
    rules: dict
    created_at: datetime
    items: list[ProcessingItemRead]


class SearchRequest(RequestModel):
    question: Annotated[NonBlankText, Field(max_length=1000)]
    top_k: int = Field(default=6, ge=1, le=20)
    strategy: Literal["bm25", "vector", "hybrid"] = "bm25"


class SearchHit(BaseModel):
    rank: int
    score: float | None
    score_kind: Literal["fts5_bm25_lower_better", "cosine_distance_lower_better", "rank_only"] = (
        "fts5_bm25_lower_better"
    )
    chunk: Chunk


class SearchResult(BaseModel):
    knowledge_base_id: str
    strategy: Literal["bm25", "vector", "hybrid"] = "bm25"
    hits: list[SearchHit]


class DemoImport(RequestModel):
    preset: Literal["travel", "technical"]
    client_request_id: UUID


class VectorBuild(RequestModel):
    model_connection_id: UUID


class EmbeddingConnectionRead(BaseModel):
    id: str
    name: str
    model_id: str


class EmployeeKnowledgeInput(RequestModel):
    expected_revision: int = Field(ge=0)
    knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=10)
    mode: Literal["on_demand", "always"] = "on_demand"
    strategy: Literal["auto", "bm25", "vector", "hybrid"] = "auto"
    top_k: int = Field(default=6, ge=1, le=12)


class EmployeeKnowledgeRead(BaseModel):
    agent_id: str
    revision: int
    knowledge_base_ids: list[str]
    mode: Literal["on_demand", "always"]
    strategy: Literal["auto", "bm25", "vector", "hybrid"]
    top_k: int
    libraries: list[LibraryRead]


class KnowledgeSearchInput(RequestModel):
    query: Annotated[
        NonBlankText, Field(max_length=1000, description="要核实的问题或关键词，可结合上下文改写。")
    ]
    library_ids: list[UUID] | None = Field(
        default=None,
        min_length=1,
        max_length=10,
        description="可选，仅收窄本轮挂载的知识库；省略或 null 时搜索全部挂载库。",
    )


class KnowledgeReadInput(RequestModel):
    evidence_id: str = Field(
        pattern=r"^K-[0-9a-f]{16}$",
        description="本轮已登记来源的证据编号，原样使用检索结果中的 evidence_id。",
    )
    offset: int = Field(
        default=0, ge=0, le=2000, description="片段内的起始字符位置，省略时从开头读取。"
    )
