"""One-process persistent Chroma storage, using only public client/collection APIs."""

import fcntl
import logging
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import IO, cast

import chromadb
from chromadb.api.client import Client
from chromadb.api.types import Embeddings, Where
from chromadb.config import Settings
from chromadb.errors import NotFoundError

from app.errors import ServiceUnavailableError
from app.knowledge.contracts import Chunk

logger = logging.getLogger(__name__)
PREFIX = "niuma_kb_"


class KnowledgeVectorStore:
    """Own the client, directory lock and collection leases; never authorize users."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.lock = RLock()
        self._client: Client | None = None
        self._file_lock: IO[str] | None = None
        self._readers: Counter[str] = Counter()
        self._retired: set[str] = set()

    @property
    def client(self) -> Client:
        with self.lock:
            if self._client is None:
                self.directory.mkdir(parents=True, exist_ok=True)
                lock = (self.directory / "writer.lock").open("a")
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._client = cast(
                        Client,
                        chromadb.PersistentClient(
                            path=str(self.directory), settings=Settings(anonymized_telemetry=False)
                        ),
                    )
                except BaseException:
                    lock.close()
                    raise
                self._file_lock = lock
            return self._client

    def close(self) -> None:
        with self.lock:
            try:
                if self._client is not None:
                    self._client.close()
            finally:
                self._client = None
                if self._file_lock:
                    self._file_lock.close()
                    self._file_lock = None

    @contextmanager
    def use(self, name: str) -> Iterator[None]:
        with self.lock:
            self._readers[name] += 1
        try:
            yield
        finally:
            with self.lock:
                self._readers[name] -= 1
                if not self._readers[name]:
                    del self._readers[name]
                self._collect()

    def build(self, name: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        collection = self.client.create_collection(
            name=name, embedding_function=None, configuration={"hnsw": {"space": "cosine"}}
        )
        size = min(256, self.client.get_max_batch_size())
        for start in range(0, len(chunks), size):
            batch = chunks[start : start + size]
            collection.add(
                ids=[chunk.id for chunk in batch],
                embeddings=cast(Embeddings, vectors[start : start + size]),
                documents=[chunk.text for chunk in batch],
                metadatas=[
                    {"chunk_id": chunk.id, "document_id": chunk.document_id} for chunk in batch
                ],
            )
        if set(collection.get(include=[])["ids"]) != {chunk.id for chunk in chunks}:
            raise ServiceUnavailableError(
                "knowledge_index_incomplete", "向量索引写入不完整，请重新构建。"
            )

    def query(
        self, name: str, vector: list[float], ids: list[str], limit: int
    ) -> list[tuple[str, float]]:
        if not ids:
            return []
        try:
            collection = self.client.get_collection(name, embedding_function=None)
            result = collection.query(
                query_embeddings=cast(Embeddings, [vector]),
                n_results=min(limit, len(ids)),
                where=cast(Where, {"chunk_id": {"$in": ids}}),
                include=["distances"],
            )
        except NotFoundError:
            raise ServiceUnavailableError(
                "knowledge_index_missing", "向量索引文件缺失，请重新建立索引。"
            ) from None
        assert result["distances"] is not None
        return list(zip(result["ids"][0], result["distances"][0], strict=True))

    def prune(self, name: str, ids: set[str]) -> None:
        collection = self.client.get_collection(name, embedding_function=None)
        stale = set(collection.get(include=[])["ids"]) - ids
        if stale:
            collection.delete(ids=sorted(stale))

    def names(self) -> set[str]:
        return {
            collection.name
            for collection in self.client.list_collections()
            if collection.name.startswith(PREFIX)
        }

    def retire(self, name: str) -> None:
        with self.lock:
            self._retired.add(name)
            self._collect()

    def _collect(self) -> None:
        for name in self._retired.copy():
            if self._readers[name]:
                continue
            try:
                self.client.delete_collection(name)
            except NotFoundError:
                pass
            except Exception:
                # Publication/removal already committed. Startup reconciliation retries.
                logger.warning("Knowledge collection cleanup deferred: %s", name)
                continue
            self._retired.remove(name)
