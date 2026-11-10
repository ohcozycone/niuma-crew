from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import timedelta
from typing import Any, cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import require_permission
from app.auth.work_authorizations import authorize_work
from app.employees.knowledge import capture_knowledge
from app.employees.references import employee_active
from app.errors import (
    AuthenticationError,
    ConflictError,
    InvalidInputError,
    PermissionDeniedError,
    ServiceError,
)
from app.execution.evidence_models import RunKnowledgeEvidence
from app.execution.knowledge_evidence import KnowledgeEvidence
from app.execution.models import Run
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.knowledge.contracts import TOOL_BINDINGS
from app.knowledge.libraries import KnowledgeLibraries, library_fact
from app.knowledge.retrieval import fuse_rankings
from app.knowledge.schemas import (
    KnowledgeReadInput,
    KnowledgeSearchInput,
    SearchHit,
    SearchRequest,
)
from app.knowledge.search import KnowledgeSearch
from app.knowledge.sources import assert_evidence
from app.runtime.contracts.content import KnowledgeResult
from app.runtime.contracts.tools import ToolInvocation
from app.values import digest, utc_now


class KnowledgeAccess:
    def __init__(self, database: Database) -> None:
        self.database = database

    def assert_current(
        self, db: Session, snapshot: Mapping[str, Any], run_id: str | None = None
    ) -> None:
        captured = snapshot.get("knowledge")
        if not captured:
            return
        if "user_id" in captured:
            raise ConflictError("knowledge_access_revoked")
        current = capture_knowledge(db, captured["agent_id"])
        active = employee_active(db, captured["agent_id"])
        ids = {item["id"] for item in captured["libraries"]}
        if (
            snapshot.get("agent_id") != captured["agent_id"]
            or not current
            or not active
            or any(current[key] != captured.get(key) for key in ("revision", "mode", "top_k"))
            or {item["id"] for item in current["libraries"]} != ids
        ):
            raise ConflictError("knowledge_access_revoked")
        for id in ids:
            if library_fact(db, id) is None:
                raise ConflictError("knowledge_access_revoked")
        if run_id:
            row = db.get(Run, run_id)
            if row is None or row.agent_id != captured["agent_id"]:
                raise ConflictError("knowledge_access_revoked")
            for evidence in db.scalars(
                select(RunKnowledgeEvidence).where(RunKnowledgeEvidence.run_id == run_id)
            ):
                assert_evidence(db, evidence, ids)

    def authorize(
        self, db: Session, snapshot: Mapping[str, Any], invocation: ToolInvocation
    ) -> dict:
        self.assert_current(db, snapshot)
        if (
            not snapshot.get("knowledge")
            or TOOL_BINDINGS.get(invocation.name) != invocation.binding_id
            or not any(
                item.get("kind") == "knowledge"
                and item.get("binding_id") == invocation.binding_id
                and item.get("exposed_name") == invocation.name
                and item.get("tool_name") == invocation.name
                for item in snapshot.get("tools", [])
            )
        ):
            raise ConflictError("tool_not_allowed")
        args = self.arguments(invocation.name, invocation.arguments)
        if isinstance(args, KnowledgeSearchInput) and args.library_ids:
            allowed = {item["id"] for item in snapshot["knowledge"]["libraries"]}
            if {str(id) for id in args.library_ids} - allowed:
                raise InvalidInputError("tool_not_allowed")
        return {
            "kind": "knowledge",
            "tool_name": invocation.name,
            "recovery": "readonly",
            "scope_policy": {},
        }

    @staticmethod
    def arguments(name: str, args: dict) -> KnowledgeSearchInput | KnowledgeReadInput:
        try:
            if name == "search_knowledge":
                return KnowledgeSearchInput.model_validate(args)
            if name == "read_knowledge_source":
                return KnowledgeReadInput.model_validate(args)
        except ValidationError:
            raise InvalidInputError("tool_arguments_invalid") from None
        raise ConflictError("tool_not_allowed")

    def run_scope(self, db: Session, run_id: str) -> tuple[Run, dict]:
        row = db.get(Run, run_id)
        if row is None or not row.config_snapshot.get("knowledge"):
            raise ConflictError("tool_not_allowed")
        self.assert_current(db, row.config_snapshot, run_id)
        if row.status != "running":
            raise ConflictError(
                "user_cancelled" if row.status == "cancelling" else "runtime_interrupted"
            )
        try:
            current = authorize_work(db, row.initiated_by_user_id, row.initiated_by_session_id)
            require_permission(current, "knowledge:use")
        except (AuthenticationError, PermissionDeniedError) as error:
            raise ConflictError("actor_session_invalid") from error
        seconds = row.config_snapshot.get("run_timeout", 120)
        if row.started_at and utc_now() - row.started_at > timedelta(seconds=seconds):
            raise ConflictError("run_timeout")
        return row, row.config_snapshot["knowledge"]

    def guard_library(self, db: Session, run_id: str, kb: str) -> None:
        """真实Run授权与员工范围共同限定内部查询，不伪造库所有者身份。"""
        _, captured = self.run_scope(db, run_id)
        if kb not in {item["id"] for item in captured["libraries"]}:
            raise ConflictError("tool_not_allowed")
        if library_fact(db, kb) is None:
            raise ConflictError("knowledge_access_revoked")


EVIDENCE_BUDGET = 18000


class RunKnowledgeSearch:
    def __init__(
        self,
        database: Database,
        access: KnowledgeAccess,
        libraries: KnowledgeLibraries,
        search: KnowledgeSearch,
        evidence: KnowledgeEvidence,
    ) -> None:
        self.database, self.access, self.libraries = database, access, libraries
        self.search, self.evidence = search, evidence

    def call(self, run_id: str, name: str, args: dict) -> KnowledgeResult:
        data = self.access.arguments(name, args)
        if isinstance(data, KnowledgeReadInput):
            return self.evidence.read_source(run_id, data)
        return self.search_run(run_id, cast(KnowledgeSearchInput, data))

    def search_run(self, run_id: str, data: KnowledgeSearchInput) -> KnowledgeResult:
        with self.database.transaction() as db:
            _, captured = self.access.run_scope(db, run_id)
            allowed = {item["id"] for item in captured["libraries"]}
        selected = (
            sorted(str(id) for id in data.library_ids) if data.library_ids else sorted(allowed)
        )
        if len(set(selected)) != len(selected) or set(selected) - allowed:
            raise InvalidInputError("tool_not_allowed")
        states: list[dict] = []
        rankings: list[list[SearchHit]] = []
        libraries: dict[str, str] = {}
        for id in selected:
            with self.database.transaction() as db:
                self.access.run_scope(db, run_id)
                self.access.guard_library(db, run_id, id)
                base = self.libraries.read_in(db, id)
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
                result = self.search.query(
                    id,
                    SearchRequest(question=data.query, top_k=min(20, captured["top_k"] * 2)),
                    lambda db: self.access.guard_library(db, run_id, id),
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
                return KnowledgeResult(
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
        with self.database.transaction() as db:
            reserve_writer(db, RunKnowledgeEvidence.__table__)
            self.access.run_scope(db, run_id)
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
                self.evidence.assert_evidence(db, evidence, allowed)
                item = self.evidence.hit(evidence)
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
        return KnowledgeResult(
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
