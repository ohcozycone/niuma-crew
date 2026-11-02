"""Private employee assembly and bounded retrieval; runtime only receives injected operations."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents.models import Agent
from app.auth.actor import Actor
from app.auth.models import AuthSession, User
from app.auth.permissions import permissions_for, require_permission
from app.errors import ConflictError, InvalidInputError, NotFoundError, ServiceError
from app.execution.models import Run
from app.infrastructure.database.fields import new_uuid, utc_now
from app.infrastructure.database.transactions import reserve_writer
from app.knowledge.contracts import Chunk, digest
from app.knowledge.models import (
    EmployeeKnowledgeLibrary,
    EmployeeKnowledgeSettings,
    KnowledgeBase,
    LibraryChunk,
    LibraryDocument,
    RunKnowledgeEvidence,
)
from app.knowledge.schemas import (
    EmployeeKnowledgeInput,
    EmployeeKnowledgeRead,
    KnowledgeReadInput,
    KnowledgeSearchInput,
    SearchRequest,
)
from app.tools.contracts import ToolInvocation, ToolOutcome

if TYPE_CHECKING:
    from app.knowledge.service import KnowledgeService

TOOL_BINDINGS = {"search_knowledge": "knowledge:search", "read_knowledge_source": "knowledge:read"}
EVIDENCE_BUDGET = 18000


class EmployeeKnowledgeService:
    def __init__(self, knowledge: KnowledgeService):
        from app.knowledge.context import KnowledgeContext

        self.knowledge = knowledge
        self.context = KnowledgeContext(self)

    @staticmethod
    def require_agent(db: Session, id: str) -> Agent:
        agent = db.get(Agent, id)
        if agent is None:
            raise NotFoundError("agent_not_found", "员工不存在。")
        return agent

    def owner(self, actor: Actor) -> str:
        require_permission(actor, "runs:create")
        return self.knowledge.owner(actor)

    @staticmethod
    def settings(db: Session, agent_id: str, user_id: str) -> EmployeeKnowledgeSettings | None:
        return db.scalar(
            select(EmployeeKnowledgeSettings).where(
                EmployeeKnowledgeSettings.agent_id == agent_id,
                EmployeeKnowledgeSettings.user_id == user_id,
            )
        )

    @staticmethod
    def library_ids(db: Session, settings: EmployeeKnowledgeSettings | None) -> list[str]:
        if settings is None:
            return []
        return list(
            db.scalars(
                select(EmployeeKnowledgeLibrary.knowledge_base_id)
                .where(
                    EmployeeKnowledgeLibrary.settings_id == settings.id,
                )
                .order_by(EmployeeKnowledgeLibrary.knowledge_base_id)
            )
        )

    def read(self, db: Session, agent_id: str, user_id: str) -> EmployeeKnowledgeRead:
        setting = self.settings(db, agent_id, user_id)
        return EmployeeKnowledgeRead(
            agent_id=agent_id,
            revision=setting.revision if setting else 0,
            knowledge_base_ids=self.library_ids(db, setting),
            mode=cast(Any, setting.mode if setting else "on_demand"),
            strategy=cast(Any, setting.strategy if setting else "auto"),
            top_k=setting.top_k if setting else 6,
            libraries=[
                self.knowledge.base_read(db, base)
                for base in db.scalars(
                    select(KnowledgeBase)
                    .where(KnowledgeBase.owner_user_id == user_id)
                    .order_by(KnowledgeBase.updated_at.desc(), KnowledgeBase.id)
                )
            ],
        )

    def get(self, actor: Actor, agent_id: str) -> EmployeeKnowledgeRead:
        user_id = self.owner(actor)
        with self.knowledge.database.transaction() as db:
            self.require_agent(db, agent_id)
            return self.read(db, agent_id, user_id)

    def replace(
        self, actor: Actor, agent_id: str, data: EmployeeKnowledgeInput
    ) -> EmployeeKnowledgeRead:
        user_id = self.owner(actor)
        ids = sorted(str(id) for id in data.knowledge_base_ids)
        if len(set(ids)) != len(ids):
            raise InvalidInputError("knowledge_duplicate_library", "不能重复装配同一知识库。")
        with self.knowledge.database.transaction() as db:
            reserve_writer(db, EmployeeKnowledgeSettings.__table__)
            self.require_agent(db, agent_id)
            for id in ids:
                self.knowledge.require_base(db, id, actor)
            setting = self.settings(db, agent_id, user_id)
            if data.expected_revision != (setting.revision if setting else 0):
                raise ConflictError(
                    "configuration_revision_conflict", "知识库装配已变化，请载入最新设置。"
                )
            if setting is None:
                setting = EmployeeKnowledgeSettings(
                    id=new_uuid(), user_id=user_id, agent_id=agent_id, revision=1
                )
                db.add(setting)
                changed = True
            else:
                changed = ids != self.library_ids(db, setting) or any(
                    getattr(setting, key) != getattr(data, key)
                    for key in ("mode", "strategy", "top_k")
                )
                if changed:
                    setting.revision += 1
            if changed:
                setting.mode, setting.strategy, setting.top_k = data.mode, data.strategy, data.top_k
                setting.updated_at = utc_now()
                db.flush()
                db.execute(
                    delete(EmployeeKnowledgeLibrary).where(
                        EmployeeKnowledgeLibrary.settings_id == setting.id
                    )
                )
                db.add_all(
                    EmployeeKnowledgeLibrary(settings_id=setting.id, knowledge_base_id=id)
                    for id in ids
                )
                db.flush()
            return self.read(db, agent_id, user_id)

    def capture(self, db: Session, agent_id: str, user_id: str | None) -> dict | None:
        if user_id is None:
            return None
        setting = self.settings(db, agent_id, user_id)
        ids = self.library_ids(db, setting)
        if not setting or not ids:
            return None
        libraries = []
        for id in ids:
            base = db.get(KnowledgeBase, id)
            if base is None or base.owner_user_id != user_id:
                raise ConflictError(
                    "knowledge_access_revoked", "知识库装配范围已变化，请重新配置。"
                )
            libraries.append({"id": id, "name": base.name, "description": base.description})
        return {
            "user_id": user_id,
            "agent_id": agent_id,
            "revision": setting.revision,
            "mode": setting.mode,
            "strategy": setting.strategy,
            "top_k": setting.top_k,
            "libraries": libraries,
        }

    def assert_current(
        self, db: Session, snapshot: Mapping[str, Any], run_id: str | None = None
    ) -> None:
        captured = snapshot.get("knowledge")
        if not captured:
            return
        setting = self.settings(db, captured["agent_id"], captured["user_id"])
        agent = db.get(Agent, captured["agent_id"])
        ids = {item["id"] for item in captured["libraries"]}
        if (
            snapshot.get("agent_id") != captured["agent_id"]
            or not setting
            or not agent
            or not agent.is_active
            or setting.revision != captured["revision"]
            or any(
                getattr(setting, key) != captured.get(key) for key in ("mode", "strategy", "top_k")
            )
            or set(self.library_ids(db, setting)) != ids
        ):
            raise ConflictError(
                "knowledge_access_revoked", "个人知识库装配已变化，请重新发送任务。"
            )
        for id in ids:
            base = db.get(KnowledgeBase, id)
            if base is None or base.owner_user_id != captured["user_id"]:
                raise ConflictError("knowledge_access_revoked", "知识库已删除或不再属于当前用户。")
        if run_id:
            row = db.get(Run, run_id)
            if (
                row is None
                or row.agent_id != captured["agent_id"]
                or row.owner_user_id != captured["user_id"]
                or row.initiated_by_user_id != captured["user_id"]
            ):
                raise ConflictError(
                    "knowledge_access_revoked", "个人知识只能用于本人发起且拥有的对话。"
                )
            for evidence in db.scalars(
                select(RunKnowledgeEvidence).where(RunKnowledgeEvidence.run_id == run_id)
            ):
                self.assert_evidence(db, evidence, ids)

    @staticmethod
    def assert_evidence(db: Session, evidence: RunKnowledgeEvidence, ids: set[str]) -> None:
        document = db.get(LibraryDocument, evidence.document_id)
        chunk = db.get(LibraryChunk, evidence.chunk_id)
        if (
            evidence.knowledge_base_id not in ids
            or document is None
            or chunk is None
            or document.knowledge_base_id != evidence.knowledge_base_id
            or document.snapshot.get("version") != evidence.document_version
            or chunk.document_id != document.id
            or chunk.snapshot != evidence.snapshot
        ):
            raise ConflictError(
                "knowledge_source_changed", "已取得的知识来源已删除或重处理，请重新提问。"
            )

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
            raise ConflictError("tool_not_allowed", "本轮没有该知识工具许可。")
        args = self.arguments(invocation.name, invocation.arguments)
        if isinstance(args, KnowledgeSearchInput) and args.library_ids:
            allowed = {item["id"] for item in snapshot["knowledge"]["libraries"]}
            if {str(id) for id in args.library_ids} - allowed:
                raise InvalidInputError("tool_not_allowed", "检索范围只能收窄已挂载的知识库。")
        return {
            "kind": "knowledge",
            "tool_name": invocation.name,
            "recovery": "readonly",
            "scope_policy": {"max_calls": 12},
        }

    @staticmethod
    def arguments(name: str, args: dict) -> KnowledgeSearchInput | KnowledgeReadInput:
        try:
            if name == "search_knowledge":
                return KnowledgeSearchInput.model_validate(args)
            if name == "read_knowledge_source":
                return KnowledgeReadInput.model_validate(args)
        except ValidationError:
            raise InvalidInputError(
                "tool_arguments_invalid", "知识工具参数无效，请检查问题、范围或证据编号。"
            ) from None
        raise ConflictError("tool_not_allowed", "没有该知识工具许可。")

    def run_scope(self, db: Session, run_id: str) -> tuple[Run, dict]:
        row = db.get(Run, run_id)
        if row is None or not row.config_snapshot.get("knowledge"):
            raise ConflictError("tool_not_allowed", "本轮没有挂载知识库。")
        self.assert_current(db, row.config_snapshot, run_id)
        if row.status != "running":
            raise ConflictError(
                "user_cancelled" if row.status == "cancelling" else "runtime_interrupted",
                "本轮已停止。",
            )
        session = (
            db.get(AuthSession, row.initiated_by_session_id)
            if row.initiated_by_session_id
            else None
        )
        user = db.get(User, row.initiated_by_user_id)
        if (
            not session
            or session.kind != "user"
            or session.user_id != row.initiated_by_user_id
            or session.revoked_at
            or session.expires_at <= utc_now()
            or not user
            or not user.is_active
        ):
            raise ConflictError("actor_session_invalid", "发起会话已失效。")
        current = Actor("user", session.id, user.id, user.username, user.role, session.expires_at)
        if not {"knowledge:use", "runs:create"} <= permissions_for(current):
            raise ConflictError("actor_session_invalid", "当前身份不再具有知识使用权限。")
        seconds = row.config_snapshot.get("run_timeout", 120)
        if row.started_at and utc_now() - row.started_at > timedelta(seconds=seconds):
            raise ConflictError("run_timeout", "知识检索超过本轮时限。")
        return row, row.config_snapshot["knowledge"]

    def call(self, run_id: str, name: str, args: dict) -> ToolOutcome:
        data = self.arguments(name, args)
        if isinstance(data, KnowledgeReadInput):
            return self.read_source(run_id, data)
        return self.search(run_id, cast(KnowledgeSearchInput, data))

    def search(self, run_id: str, data: KnowledgeSearchInput) -> ToolOutcome:
        with self.knowledge.database.transaction() as db:
            _, captured = self.run_scope(db, run_id)
            allowed = {item["id"] for item in captured["libraries"]}
        selected = (
            sorted(str(id) for id in data.library_ids) if data.library_ids else sorted(allowed)
        )
        if len(set(selected)) != len(selected) or set(selected) - allowed:
            raise InvalidInputError("tool_not_allowed", "检索范围只能收窄本轮挂载的知识库。")
        actor = Actor("user", "", captured["user_id"], "", "member", utc_now() + timedelta(hours=1))
        states: list[dict] = []
        ranked: list[tuple[float, str, Chunk]] = []
        for id in selected:
            with self.knowledge.database.transaction() as db:
                self.run_scope(db, run_id)
                base = self.knowledge.base_read(db, self.knowledge.require_base(db, id, actor))
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
            strategy = captured["strategy"]
            if strategy == "auto":
                strategy = "hybrid" if base.vector_status in {"ready", "partial"} else "bm25"
            try:
                result = self.knowledge.search(
                    actor,
                    id,
                    SearchRequest(
                        question=data.query, top_k=min(20, captured["top_k"] * 2), strategy=strategy
                    ),
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
                    if base.vector_status == "partial" and strategy != "bm25"
                    else "ready"
                    if result.hits
                    else "no_match",
                    "strategy": strategy,
                }
            )
            ranked.extend(
                (1 / (60 + rank), id, hit.chunk) for rank, hit in enumerate(result.hits, 1)
            )
        ranked.sort(key=lambda item: (-item[0], item[1], item[2].id))
        hits: list[dict] = []
        with self.knowledge.database.transaction() as db:
            reserve_writer(db, RunKnowledgeEvidence.__table__)
            self.run_scope(db, run_id)
            for _, kb, chunk in ranked:
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
                self.assert_evidence(db, evidence, allowed)
                item = self.hit(evidence)
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

    @staticmethod
    def hit(evidence: RunKnowledgeEvidence, offset: int = 0, limit: int = 800) -> dict:
        chunk = Chunk.model_validate(evidence.snapshot)
        end = min(len(chunk.text), offset + limit)
        return {
            "evidence_id": evidence.evidence_id,
            "knowledge_base_id": evidence.knowledge_base_id,
            "document_id": evidence.document_id,
            "chunk_id": evidence.chunk_id,
            "title": chunk.title[:300],
            "locator": chunk.locator[:600],
            "content": chunk.text[offset:end],
            "offset": offset,
            "next_offset": end if end < len(chunk.text) else None,
            "total_chars": len(chunk.text),
            "source_url": f"/knowledge/{evidence.knowledge_base_id}/documents/{evidence.document_id}?chunk={evidence.chunk_id}",
        }

    def read_source(self, run_id: str, data: KnowledgeReadInput) -> ToolOutcome:
        with self.knowledge.database.transaction() as db:
            self.run_scope(db, run_id)
            evidence = db.get(RunKnowledgeEvidence, (run_id, data.evidence_id))
            if evidence is None:
                raise NotFoundError(
                    "knowledge_evidence_not_found", "该证据不属于本轮已取得的来源。"
                )
            result = self.hit(evidence, data.offset, 2000)
        return ToolOutcome(
            json.dumps(result, ensure_ascii=False),
            sources=(
                {
                    "title": result["title"],
                    "url": result["source_url"],
                    "status": "succeeded",
                    "full_text": False,
                },
            ),
        )

    def finalize_answer(self, run_id: str, text: str, db: Session | None = None) -> str:
        """Restore only a missing root slash for an exact, authorized evidence/link pair."""
        if db is None:
            with self.knowledge.database.transaction() as session:
                return self.finalize_answer(run_id, text, session)
        self.run_scope(db, run_id)
        urls: dict[str, str] = {
            item.evidence_id: self.hit(item)["source_url"]
            for item in db.scalars(
                select(RunKnowledgeEvidence).where(RunKnowledgeEvidence.run_id == run_id)
            )
        }

        def restore_slash(match: re.Match[str]) -> str:
            identifier, target = match.groups()
            canonical = urls.get(identifier)
            if canonical == "/" + target:
                return f"[{identifier}]({canonical})"
            return match.group()

        # Do not resolve arbitrary URLs or infer sources from label text. The exact
        # registered pair is the authority; raw model actions remain unchanged.
        text = re.sub(r"\[(K-[a-f0-9]{16})\]\((knowledge/[^\s)]+)\)", restore_slash, text)
        self.verify_answer(run_id, text, db)
        return text

    def verify_answer(self, run_id: str, text: str, db: Session | None = None) -> None:
        if db is None:
            with self.knowledge.database.transaction() as session:
                self.verify_answer(run_id, text, session)
            return
        self.run_scope(db, run_id)
        evidence = list(
            db.scalars(select(RunKnowledgeEvidence).where(RunKnowledgeEvidence.run_id == run_id))
        )
        ids = {item.evidence_id for item in evidence}
        urls = {self.hit(item)["source_url"] for item in evidence}
        by_id = {item.evidence_id: self.hit(item)["source_url"] for item in evidence}
        invalid = set(re.findall(r"\bK-[a-zA-Z0-9_-]+", text)) - ids
        # Match the entire target, including arbitrary schemes and relative prefixes.
        # Searching only for /knowledge would falsely accept sandbox:/knowledge/...
        # by discarding its disallowed prefix before authorization.
        links = re.findall(r"\[([^\]]*)\]\(\s*<?([^\s)>]+)", text)
        for label, target in links:
            if label in by_id and target != by_id[label]:
                invalid.add(target)
        targets = [target for _, target in links]
        targets += re.findall(r"[^\s()\[\]<>`]*knowledge/[^\s()\[\]<>`]+", text)
        for raw in targets:
            internal = (
                raw.startswith(("/knowledge/", "knowledge/", "./knowledge/"))
                or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:/knowledge/", raw)
                or re.search(r"/knowledge/[0-9a-fA-F-]{36}/documents/", raw)
            )
            if internal and raw not in urls:
                invalid.add(raw)
        if invalid:
            raise InvalidInputError(
                "knowledge_citation_invalid", "回答包含未在本轮取得或不匹配的知识来源，未发布结果。"
            )
