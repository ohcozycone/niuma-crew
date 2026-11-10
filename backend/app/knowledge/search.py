from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.errors import ConflictError
from app.infrastructure.database.session import Database
from app.knowledge.lexical import lexical_search
from app.knowledge.libraries import KnowledgeLibraries
from app.knowledge.models import KnowledgeBase
from app.knowledge.schemas import (
    SearchRequest,
    SearchResult,
)
from app.knowledge.vectors import KnowledgeVectorService


class KnowledgeSearch:
    lexical_search = staticmethod(lexical_search)

    def __init__(
        self, database: Database, libraries: KnowledgeLibraries, vectors: KnowledgeVectorService
    ) -> None:
        self.database, self.libraries, self.vectors = database, libraries, vectors

    def search_library(self, actor: Actor, kb_id: str, data: SearchRequest) -> SearchResult:
        if actor.kind == "guest":
            if data.strategy in {"vector", "hybrid"}:
                from app.auth.permissions import require_permission

                require_permission(actor, "knowledge:manage")
            data = data.model_copy(update={"strategy": "bm25"})
        else:
            self.libraries.manager(actor)

        def guard(db: Session) -> None:
            self.libraries.require_base(db, kb_id, actor)

        return self.query(kb_id, data, guard)

    def query(
        self, kb_id: str, data: SearchRequest, guard: Callable[[Session], None]
    ) -> SearchResult:
        """管理测试与受管Run共用检索核心，各自的授权在每次读取/发布前复核。"""

        def authorize(db: Session) -> KnowledgeBase:
            guard(db)
            base = db.get(KnowledgeBase, kb_id)
            if base is None:
                raise ConflictError("knowledge_access_revoked", "知识库已删除或不可用。")
            return base

        with self.database.transaction() as session:
            base = authorize(session)
            summary = self.libraries.base_read(session, base)
            if data.strategy == "auto":
                data = data.model_copy(
                    update={
                        "strategy": "hybrid"
                        if summary.vector_status in {"ready", "partial"}
                        else "bm25"
                    }
                )
            if data.strategy == "bm25":
                return SearchResult(
                    knowledge_base_id=kb_id,
                    hits=lexical_search(session, kb_id, data.question, data.top_k),
                )
        return self.vectors.query(kb_id, data, authorize)
