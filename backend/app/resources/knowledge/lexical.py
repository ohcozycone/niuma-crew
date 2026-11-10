import hashlib
import re
import sqlite3
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.common.values import digest
from app.resources.knowledge.contracts import Chunk
from app.resources.knowledge.models import LibraryDocument
from app.resources.knowledge.schemas import SearchHit


@lru_cache(maxsize=1)
def _lexical_tokenizer() -> Any:
    import jieba  # type: ignore[import-untyped]

    return jieba.Tokenizer()


def lexical_version() -> str:
    import jieba

    dictionary = Path(jieba.__file__).with_name("dict.txt")
    return digest(
        [
            "poc-lexical-v1",
            version("jieba"),
            hashlib.sha256(dictionary.read_bytes()).hexdigest(),
            sqlite3.sqlite_version,
        ]
    )


def lexical_terms(text: str) -> tuple[str, ...]:
    return tuple(
        word
        for word in _lexical_tokenizer().cut(text.casefold(), HMM=False)
        if re.search(r"\w", word)
    )


def lexical_search(session: Session, kb_id: str, question: str, top_k: int) -> list[SearchHit]:
    """调用方检查归属；混合检索与向量候选使用同一快照。"""
    terms = tuple(dict.fromkeys(lexical_terms(question)))[:64]
    query = " OR ".join('"' + word.replace('"', '""') + '"' for word in terms)
    lexical = lexical_version()
    incompatible = session.scalar(
        select(LibraryDocument.id)
        .where(
            LibraryDocument.knowledge_base_id == kb_id,
            LibraryDocument.lexical_version != "",
            LibraryDocument.lexical_version != lexical,
        )
        .limit(1)
    )
    if incompatible:
        raise ConflictError("knowledge_index_outdated", "分词规则已变化，请重新导入资料后检索。")
    hits = []
    if query:
        rows = session.execute(
            text("""SELECT knowledge_chunks.snapshot, bm25(knowledge_fts) AS score
            FROM knowledge_fts JOIN knowledge_chunks ON knowledge_chunks.id=knowledge_fts.chunk_id
            JOIN knowledge_documents ON knowledge_documents.id=knowledge_chunks.document_id
            WHERE knowledge_fts MATCH :query AND knowledge_fts.knowledge_base_id=:kb
            AND knowledge_documents.knowledge_base_id=:kb
            ORDER BY score, knowledge_fts.chunk_id LIMIT :limit"""),
            {"query": query, "kb": kb_id, "limit": top_k},
        ).all()
        for i, (snapshot, score) in enumerate(rows, 1):
            hits.append(
                SearchHit(
                    rank=i,
                    score=cast(float, score),
                    chunk=Chunk.model_validate_json(cast(str, snapshot)),
                )
            )
    return hits
