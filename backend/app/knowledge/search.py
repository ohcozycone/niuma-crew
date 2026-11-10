from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.builtin_tools.contracts import ToolOutcome
from app.errors import ConflictError, InvalidInputError, ServiceError
from app.infrastructure.database.transactions import reserve_writer
from app.knowledge.contracts import Chunk
from app.knowledge.lexical import lexical_terms, lexical_version
from app.knowledge.models import (
    KnowledgeBase,
    LibraryDocument,
    RunKnowledgeEvidence,
)
from app.knowledge.retrieval import fuse_rankings
from app.knowledge.schemas import (
    KnowledgeReadInput,
    KnowledgeSearchInput,
    SearchHit,
    SearchRequest,
    SearchResult,
)
from app.values import digest

if TYPE_CHECKING:
    from app.knowledge.service import KnowledgeService


EVIDENCE_BUDGET = 18000


class KnowledgeSearch:
    def __init__(self, knowledge: KnowledgeService) -> None:
        self.knowledge = knowledge

    def call(self, run_id: str, name: str, args: dict) -> ToolOutcome:
        data = self.knowledge.access.arguments(name, args)
        if isinstance(data, KnowledgeReadInput):
            return self.knowledge.evidence.read_source(run_id, data)
        return self.search_run(run_id, cast(KnowledgeSearchInput, data))

    def search_run(self, run_id: str, data: KnowledgeSearchInput) -> ToolOutcome:
        with self.knowledge.database.transaction() as db:
            _, captured = self.knowledge.access.run_scope(db, run_id)
            allowed = {item["id"] for item in captured["libraries"]}
        selected = (
            sorted(str(id) for id in data.library_ids) if data.library_ids else sorted(allowed)
        )
        if len(set(selected)) != len(selected) or set(selected) - allowed:
            raise InvalidInputError("tool_not_allowed", "检索范围只能收窄本轮挂载的知识库。")
        states: list[dict] = []
        rankings: list[list[SearchHit]] = []
        libraries: dict[str, str] = {}
        for id in selected:
            with self.knowledge.database.transaction() as db:
                self.knowledge.access.run_scope(db, run_id)
                base = self.knowledge.base_read(db, self.knowledge.access.run_base(db, run_id, id))
            coverage = {
                "documents": base.document_count,
                "keyword_documents": base.keyword_document_count,
                "pending_documents": base.document_count - base.keyword_document_count,
                "vector_status": base.vector_status,
                "vector_chunks": base.vector_chunk_count,
                "chunks": base.chunk_count,
            }
            if not base.chunk_count:
                states.append(
                    {
                        "id": id,
                        **coverage,
                        "status": "pending" if base.document_count else "empty",
                        "strategy": "bm25",
                    }
                )
                continue
            try:
                result = self.query(
                    id,
                    SearchRequest(question=data.query, top_k=min(20, captured["top_k"] * 2)),
                    lambda db: self.knowledge.access.run_base(db, run_id, id),
                )
            except ServiceError as error:
                payload = {
                    "status": "failed",
                    "hits": [],
                    "libraries": [
                        *states,
                        {
                            "id": id,
                            **coverage,
                            "status": "failed",
                            "code": error.code,
                            "message": error.message,
                        },
                    ],
                }
                return ToolOutcome(
                    json.dumps(payload, ensure_ascii=False), "failed", {"query": data.query}
                )
            states.append(
                {
                    "id": id,
                    **coverage,
                    "status": "partial"
                    if base.vector_status == "partial" and result.strategy != "bm25"
                    else "ready"
                    if result.hits
                    else "no_match",
                    "strategy": result.strategy,
                }
            )
            rankings.append(result.hits)
            libraries.update((hit.chunk.id, id) for hit in result.hits)
        ranked = fuse_rankings(rankings, sum(len(ranking) for ranking in rankings))
        hits: list[dict] = []
        with self.knowledge.database.transaction() as db:
            reserve_writer(db, RunKnowledgeEvidence.__table__)
            self.knowledge.access.run_scope(db, run_id)
            for hit in ranked:
                chunk = hit.chunk
                kb = libraries[chunk.id]
                id = "K-" + digest([run_id, kb, chunk.id])[:16]
                evidence = RunKnowledgeEvidence(
                    run_id=run_id,
                    evidence_id=id,
                    knowledge_base_id=kb,
                    document_id=chunk.document_id,
                    document_version=chunk.document_version,
                    chunk_id=chunk.id,
                    snapshot=chunk.model_dump(mode="json"),
                )
                self.knowledge.evidence.assert_evidence(db, evidence, allowed)
                item = self.knowledge.evidence.hit(evidence)
                if (
                    len(
                        json.dumps(
                            {"hits": [*hits, item], "libraries": states}, ensure_ascii=False
                        ).encode()
                    )
                    > EVIDENCE_BUDGET
                ):
                    continue
                if db.get(RunKnowledgeEvidence, (run_id, id)) is None:
                    db.add(evidence)
                hits.append(item)
                if len(hits) >= captured["top_k"]:
                    break
            db.flush()
        status = (
            "ok"
            if hits
            else "pending"
            if states and all(item["status"] in {"pending", "empty"} for item in states)
            else "no_match"
        )
        return ToolOutcome(
            json.dumps(
                {"status": status, "hits": hits, "libraries": states, "untrusted_data": True},
                ensure_ascii=False,
            ),
            data={"query": data.query},
            sources=tuple(
                {
                    "title": item["title"],
                    "url": item["source_url"],
                    "status": "succeeded",
                    "full_text": False,
                }
                for item in hits
            ),
        )

    def search_library(self, actor: Actor, kb_id: str, data: SearchRequest) -> SearchResult:
        if actor.kind == "guest":
            if data.strategy in {"vector", "hybrid"}:
                from app.auth.permissions import require_permission

                require_permission(actor, "knowledge:manage")
            data = data.model_copy(update={"strategy": "bm25"})
        else:
            self.knowledge.manager(actor)
        return self.query(kb_id, data, lambda db: self.knowledge.require_base(db, kb_id, actor))

    def query(
        self, kb_id: str, data: SearchRequest, authorize: Callable[[Session], KnowledgeBase]
    ) -> SearchResult:
        """管理测试与受管Run共用检索核心，各自的授权在每次读取/发布前复核。"""
        with self.knowledge.database.transaction() as session:
            base = authorize(session)
            summary = self.knowledge.base_read(session, base)
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
                    hits=self.lexical_search(session, kb_id, data.question, data.top_k),
                )
        return self.knowledge.vectors.query(kb_id, data, authorize)

    @staticmethod
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
            raise ConflictError(
                "knowledge_index_outdated", "分词规则已变化，请重新导入资料后检索。"
            )
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
