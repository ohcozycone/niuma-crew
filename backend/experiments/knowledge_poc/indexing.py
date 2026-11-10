import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from chromadb import PersistentClient
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from app.common.values import digest
from app.resources.knowledge.contracts import Chunk, Guard, KnowledgeDocument
from app.resources.knowledge.lexical import lexical_terms, lexical_version
from experiments.knowledge_poc.contracts import RetrievalPreset


class CheckedEmbeddings(Embeddings):
    """校验上游向量，避免把短响应、NaN 或空间变化写进索引。"""

    def __init__(self, delegate: Embeddings, dimension: int | None = None):
        self.delegate, self.dimension = delegate, dimension

    def _check(self, vectors: list[list[float]], expected: int) -> list[list[float]]:
        if len(vectors) != expected:
            raise ValueError("embedding response count mismatch")
        for vector in vectors:
            if not vector or not all(math.isfinite(v) for v in vector):
                raise ValueError("embedding contains empty or non-finite vector")
            if self.dimension is None:
                self.dimension = len(vector)
            if len(vector) != self.dimension:
                raise ValueError("embedding dimension mismatch")
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._check(self.delegate.embed_documents(texts), len(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._check([self.delegate.embed_query(text)], 1)[0]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def release_path(root: Path, scope_id: str, release_id: str) -> Path:
    for value in (scope_id, release_id):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", value):
            raise ValueError("invalid scope or release identifier")
    return root / "releases" / scope_id / release_id


def vector_store(
    root: Path, collection: str, embeddings: Embeddings, *, create: bool = False
) -> Chroma:
    client = PersistentClient(
        path=str(root / "chroma"), settings=Settings(anonymized_telemetry=False)
    )
    return Chroma(
        client=client,
        collection_name=collection,
        embedding_function=embeddings,
        collection_metadata={"hnsw:space": "cosine"},
        create_collection_if_not_exists=create,
    )


def save_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def build_release(
    root: Path,
    scope_id: str,
    documents: tuple[KnowledgeDocument, ...],
    chunks: tuple[Chunk, ...],
    embeddings: Embeddings,
    *,
    space_id: str,
    preset: RetrievalPreset,
    tokenizer: str,
    embedding_kind: str = "semantic_api",
    guard: Guard = lambda: None,
) -> str:
    """事务外构建；只有完整制品可打开，失败不覆盖以前发布。"""
    if not documents or not chunks or len(chunks) > 5000:
        raise ValueError("POC requires 1..5000 chunks")
    if len({c.id for c in chunks}) != len(chunks):
        raise ValueError("duplicate chunk id")
    if len({d.id for d in documents}) != len(documents):
        raise ValueError("duplicate document id")
    validate_sources(documents, chunks)
    release_id = uuid4().hex
    target = release_path(root, scope_id, release_id)
    staging = root / ".building" / release_id
    staging.mkdir(parents=True, exist_ok=False)
    collection = "kb_" + digest([scope_id, release_id])[:48]
    checked = CheckedEmbeddings(embeddings)
    store = None
    try:
        guard()
        save_json(staging / "documents.json", [d.model_dump(mode="json") for d in documents])
        save_json(staging / "chunks.json", [c.model_dump(mode="json") for c in chunks])
        with closing(sqlite3.connect(staging / "index.sqlite3")) as db:
            db.execute(
                "CREATE VIRTUAL TABLE chunks USING fts5(title_terms,body_terms,chunk_id UNINDEXED)"
            )
            db.executemany(
                "INSERT INTO chunks VALUES (?,?,?)",
                [
                    (
                        " ".join(lexical_terms(c.title + " " + c.locator)),
                        " ".join(lexical_terms(c.text)),
                        c.id,
                    )
                    for c in chunks
                ],
            )
            db.commit()
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("FTS5 integrity check failed")
        store = vector_store(root, collection, checked, create=True)
        for offset in range(0, len(chunks), 16):
            guard()
            batch = chunks[offset : offset + 16]
            store.add_texts(
                texts=[c.index_text for c in batch],
                ids=[c.id for c in batch],
                metadatas=[{"chunk_id": c.id, "release_id": release_id} for c in batch],
            )
        ids = store.get(include=[])["ids"]
        if len(ids) != len(chunks) or set(ids) != {c.id for c in chunks}:
            raise ValueError("vector index id set mismatch")
        guard()
        manifest = {
            "schema_version": 1,
            "scope_id": scope_id,
            "release_id": release_id,
            "collection": collection,
            "space_id": space_id,
            "dimension": checked.dimension,
            "embedding_kind": embedding_kind,
            "tokenizer": tokenizer,
            "lexical_version": lexical_version(),
            "preset": preset.model_dump(),
            "count": len(chunks),
            "files": {
                name: file_hash(staging / name)
                for name in ("documents.json", "chunks.json", "index.sqlite3")
            },
        }
        save_json(staging / "manifest.json", manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(target)
        return release_id
    except BaseException as error:
        try:
            if store is not None:
                store.delete_collection()
        except Exception as cleanup_error:
            error.add_note(f"orphan collection cleanup failed: {type(cleanup_error).__name__}")
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_sources(documents: tuple[KnowledgeDocument, ...], chunks: tuple[Chunk, ...]) -> None:
    by_id = {d.id: d for d in documents}
    for chunk in chunks:
        doc = by_id.get(chunk.document_id)
        if doc is None or doc.version != chunk.document_version:
            raise ValueError("chunk references wrong document version")
        if not 0 <= chunk.start < chunk.end <= len(doc.text):
            raise ValueError("chunk range is invalid")
        blocks = {b.id: b for b in doc.blocks}
        text, absolute = "", chunk.start
        for span in chunk.spans:
            block = blocks.get(span.block_id)
            if block is None or not 0 <= span.start < span.end <= block.end - block.start:
                raise ValueError("source span is invalid")
            if block.start + span.start != absolute:
                raise ValueError("source spans are not contiguous")
            text += doc.text[block.start + span.start : block.start + span.end]
            absolute = block.start + span.end
        if text != chunk.text or absolute != chunk.end:
            raise ValueError("source spans do not reconstruct chunk")


class Release:
    """已核对文件摘要、固定范围与两路 ID 的只读发布视图。"""

    def __init__(
        self, root: Path, scope_id: str, release_id: str, embeddings: Embeddings, space_id: str
    ):
        self.path = release_path(root.resolve(), scope_id, release_id)
        self.manifest = json.loads((self.path / "manifest.json").read_text())
        m = self.manifest
        if m["schema_version"] != 1 or m["scope_id"] != scope_id or m["release_id"] != release_id:
            raise ValueError("release scope or schema mismatch")
        if m["space_id"] != space_id:
            raise ValueError("embedding space mismatch")
        if m["lexical_version"] != lexical_version():
            raise ValueError("lexical tokenizer version mismatch")
        if m["collection"] != "kb_" + digest([scope_id, release_id])[:48]:
            raise ValueError("collection does not belong to release")
        if set(m["files"]) != {"documents.json", "chunks.json", "index.sqlite3"}:
            raise ValueError("invalid release file set")
        for name, checksum in m["files"].items():
            if file_hash(self.path / name) != checksum:
                raise ValueError("release file hash mismatch")
        self.documents = tuple(
            KnowledgeDocument.model_validate(d)
            for d in json.loads((self.path / "documents.json").read_text())
        )
        self.chunks = {
            c["id"]: Chunk.model_validate(c)
            for c in json.loads((self.path / "chunks.json").read_text())
        }
        if len(self.chunks) != m["count"]:
            raise ValueError("chunk count mismatch")
        validate_sources(self.documents, tuple(self.chunks.values()))
        self.store = vector_store(
            root, m["collection"], CheckedEmbeddings(embeddings, m["dimension"])
        )
        vector_ids = self.store.get(include=[])["ids"]
        with closing(self.connect_lexical()) as db:
            lexical_ids = [r[0] for r in db.execute("SELECT chunk_id FROM chunks")]
        if any(
            len(ids) != len(self.chunks) or set(ids) != set(self.chunks)
            for ids in (lexical_ids, vector_ids)
        ):
            raise ValueError("release indexes disagree")

    def connect_lexical(self) -> sqlite3.Connection:
        return sqlite3.connect((self.path / "index.sqlite3").as_uri() + "?mode=ro", uri=True)
