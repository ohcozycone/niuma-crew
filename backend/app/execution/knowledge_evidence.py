from __future__ import annotations

import json
import re
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.errors import ConflictError, InvalidInputError, NotFoundError
from app.execution.evidence_models import RunKnowledgeEvidence
from app.execution.models import Run
from app.execution.store import require_run
from app.infrastructure.database.session import Database
from app.knowledge.contracts import Chunk
from app.knowledge.schemas import (
    KnowledgeEvidenceRead,
    KnowledgeEvidenceReference,
    KnowledgeReadInput,
)
from app.knowledge.sources import assert_evidence, context_revision
from app.runtime.contracts.content import KnowledgeResult

LINK = re.compile(r"\[([^\]]*)\]\(([^\s)]+)\)")


class KnowledgeEvidence:
    context_revision = staticmethod(context_revision)
    assert_evidence = staticmethod(assert_evidence)

    def __init__(
        self, database: Database, *, run_scope: Callable[[Session, str], tuple[Run, dict]]
    ) -> None:
        self.database, self.run_scope = database, run_scope

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
            "source_url": KnowledgeEvidence.source_url(evidence),
        }

    def citation_hit(
        self, db: Session, evidence: RunKnowledgeEvidence, offset: int = 0, limit: int = 800
    ) -> dict:
        result = self.hit(evidence, offset, limit)
        row = db.get(Run, evidence.run_id)
        if row is None:
            raise ConflictError("knowledge_source_changed")
        for item in row.config_snapshot.get("knowledge", {}).get("history_evidence", []):
            if item["evidence_id"] != evidence.evidence_id:
                continue
            match = re.fullmatch(
                r"/knowledge/sources/([1-9][0-9]{11})/(K-[0-9a-f]{16})", item["source_url"]
            )
            source = db.get(RunKnowledgeEvidence, (match[1], match[2])) if match else None
            source_run = db.get(Run, match[1]) if match else None
            if (
                source is None
                or source_run is None
                or source.snapshot != evidence.snapshot
                or source_run.agent_id != row.agent_id
                or source_run.owner_user_id != row.owner_user_id
                or source_run.thread_id != row.thread_id
                or not self.frozen_scope(source_run, source)
            ):
                raise ConflictError("knowledge_source_changed")
            result["source_url"] = item["source_url"]
            break
        return result

    def read_source(self, run_id: str, data: KnowledgeReadInput) -> KnowledgeResult:
        with self.database.transaction() as db:
            self.run_scope(db, run_id)
            evidence = db.get(RunKnowledgeEvidence, (run_id, data.evidence_id))
            if evidence is None:
                raise NotFoundError("knowledge_evidence_not_found")
            result = self.citation_hit(db, evidence, data.offset, 2000)
        return KnowledgeResult(
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
        """在同一授权事务中规范化并核验引用。"""
        if db is None:
            with self.database.transaction() as session:
                return self.finalize_answer(run_id, text, session)
        self.run_scope(db, run_id)
        by_id = {
            item.evidence_id: self.citation_hit(db, item)["source_url"]
            for item in db.scalars(
                select(RunKnowledgeEvidence).where(RunKnowledgeEvidence.run_id == run_id)
            )
        }

        def restore_slash(match: re.Match[str]) -> str:
            identifier, target = match.groups()
            canonical = by_id.get(identifier)
            if canonical == "/" + target:
                return f"[{identifier}]({canonical})"
            return match.group()

        # 引用资格以已登记的精确配对为准，不从 URL 猜测。
        text = re.sub(r"\[(K-[a-f0-9]{16})\]\((knowledge/[^\s)]+)\)", restore_slash, text)
        ids, urls = set(by_id), set(by_id.values())
        invalid = set(re.findall(r"\bK-[a-zA-Z0-9_-]+", text)) - ids
        # 匹配完整目标，避免丢弃 sandbox: 等前缀后误认成合法知识引用。
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
                or re.search(r"/knowledge/sources/[1-9][0-9]{11}/K-[0-9a-f]{16}", raw)
            )
            if internal and raw not in urls:
                invalid.add(raw)
        if invalid:
            raise InvalidInputError("knowledge_citation_invalid")
        return text

    @staticmethod
    def source_url(evidence: RunKnowledgeEvidence) -> str:
        return f"/knowledge/sources/{evidence.run_id}/{evidence.evidence_id}"

    @staticmethod
    def legacy_url(evidence: RunKnowledgeEvidence) -> str:
        return f"/knowledge/{evidence.knowledge_base_id}/documents/{evidence.document_id}?chunk={evidence.chunk_id}"

    @staticmethod
    def frozen_scope(row: Run, evidence: RunKnowledgeEvidence) -> bool:
        """历史来源只按原Run冻结范围核验，不读取已退役的个人设置。"""
        captured = row.config_snapshot.get("knowledge")
        if not captured or captured.get("agent_id") != row.agent_id:
            return False
        if evidence.knowledge_base_id not in {item["id"] for item in captured.get("libraries", [])}:
            return False
        legacy_user = captured.get("user_id")
        return legacy_user is None or legacy_user == row.owner_user_id == row.initiated_by_user_id

    @staticmethod
    def source_run(
        db: Session, run_id: str, captured: dict, *, owner_user_id: str, thread_id: str
    ) -> Run | None:
        row = db.get(Run, run_id)
        if (
            row is None
            or row.status != "succeeded"
            or row.origin_kind != "conversation"
            or row.agent_id != captured["agent_id"]
            or row.owner_user_id != owner_user_id
            or row.thread_id != thread_id
        ):
            return None
        return row

    def readable_run(self, db: Session, actor: Actor, run_id: str) -> Run:
        require_permission(actor, "knowledge:use")
        require_permission(actor, "runs:read")
        return require_run(db, run_id, actor)

    def preview(
        self, actor: Actor, run_id: str, evidence_id: str, offset: int = 0
    ) -> KnowledgeEvidenceRead:
        with self.database.transaction() as db:
            row = self.readable_run(db, actor, run_id)
            evidence = db.get(RunKnowledgeEvidence, (run_id, evidence_id))
            if evidence is None or not self.frozen_scope(row, evidence):
                raise NotFoundError("knowledge_evidence_not_found")
            assert_evidence(db, evidence, {evidence.knowledge_base_id})
            return KnowledgeEvidenceRead(
                **{
                    key: value
                    for key, value in self.citation_hit(db, evidence, offset, 2000).items()
                    if key in KnowledgeEvidenceRead.model_fields
                },
                document_version=evidence.document_version,
            )

    def references(self, actor: Actor, run_id: str) -> list[KnowledgeEvidenceReference]:
        """供旧回答精确映射已有引用；仅返回该Run已登记的有界目录。"""
        with self.database.transaction() as db:
            row = self.readable_run(db, actor, run_id)
            result = []
            for evidence in db.scalars(
                select(RunKnowledgeEvidence)
                .where(RunKnowledgeEvidence.run_id == run_id)
                .order_by(RunKnowledgeEvidence.evidence_id)
                .limit(240)
            ):
                if self.frozen_scope(row, evidence):
                    result.append(
                        KnowledgeEvidenceReference(
                            evidence_id=evidence.evidence_id,
                            title=evidence.snapshot["title"][:300],
                            source_url=self.citation_hit(db, evidence)["source_url"],
                            legacy_source_url=self.legacy_url(evidence),
                        )
                    )
            return result

    def capture_history(
        self,
        db: Session,
        captured: dict,
        history: list[tuple[str, str]],
        budget: int,
        *,
        owner_user_id: str,
        thread_id: str,
    ) -> list[dict]:
        """仅接收宿主选定且已成功接纳的回复。"""
        result: list[dict] = []
        seen: set[str] = set()
        allowed = {item["id"] for item in captured["libraries"]}
        for run_id, content in reversed(history):
            source = self.source_run(
                db, run_id, captured, owner_user_id=owner_user_id, thread_id=thread_id
            )
            if source is None:
                continue
            for identifier, url in LINK.findall(content):
                if identifier in seen:
                    continue
                evidence = db.get(RunKnowledgeEvidence, (run_id, identifier))
                if (
                    evidence is None
                    or not self.frozen_scope(source, evidence)
                    or url
                    not in {
                        self.citation_hit(db, evidence)["source_url"],
                        self.legacy_url(evidence),
                    }
                ):
                    continue
                try:
                    assert_evidence(db, evidence, allowed)
                except ConflictError:
                    continue
                item = {
                    "source_run_id": run_id,
                    "matched_source_url": url,
                    **self.citation_hit(db, evidence),
                }
                if len(json.dumps([*result, item], ensure_ascii=False).encode()) > min(
                    18000, budget
                ):
                    continue
                result.append(item)
                seen.add(identifier)
                if len(result) >= captured["top_k"]:
                    return result
        return result

    def bind_history(self, db: Session, row: Run) -> None:
        """受理前仅登记快照选定的历史引用。"""
        captured = row.config_snapshot.get("knowledge", {})
        allowed = {item["id"] for item in captured.get("libraries", [])}
        for item in captured.get("history_evidence", []):
            source = self.source_run(
                db,
                item["source_run_id"],
                captured,
                owner_user_id=row.owner_user_id,
                thread_id=row.thread_id,
            )
            evidence = db.get(RunKnowledgeEvidence, (item["source_run_id"], item["evidence_id"]))
            if (
                source is None
                or evidence is None
                or not self.frozen_scope(source, evidence)
                or item.get("matched_source_url")
                not in {self.citation_hit(db, evidence)["source_url"], self.legacy_url(evidence)}
                or item
                != {
                    "source_run_id": source.id,
                    "matched_source_url": item.get("matched_source_url"),
                    **self.citation_hit(db, evidence),
                }
            ):
                raise ConflictError("knowledge_source_changed")
            assert_evidence(db, evidence, allowed)
            db.add(
                RunKnowledgeEvidence(
                    run_id=row.id,
                    evidence_id=evidence.evidence_id,
                    knowledge_base_id=evidence.knowledge_base_id,
                    document_id=evidence.document_id,
                    document_version=evidence.document_version,
                    chunk_id=evidence.chunk_id,
                    snapshot=evidence.snapshot,
                )
            )

    @staticmethod
    def clean_history(content: str, evidence: list[dict]) -> str:
        """仅清理送模副本中的引用资格，不改已保存历史。"""
        urls = {item["evidence_id"]: item["source_url"] for item in evidence}
        matches = {
            (item["evidence_id"], item.get("matched_source_url", item["source_url"])): item[
                "source_url"
            ]
            for item in evidence
        }

        def replace(match: re.Match[str]) -> str:
            label, target = match.groups()
            internal = target.startswith(
                ("/knowledge/", "knowledge/", "./knowledge/")
            ) or re.search(r"/knowledge/[0-9a-fA-F-]{36}/documents/", target)
            if internal:
                canonical = matches.get((label, target))
                if canonical:
                    return f"[{label}]({canonical})"
                if urls.get(label) != target:
                    return "（历史知识来源未纳入本轮，请重新检索）"
            return match.group()

        content = LINK.sub(replace, content)
        return re.sub(
            r"\bK-[a-zA-Z0-9_-]+",
            lambda match: match.group() if match.group() in urls else "历史证据（需重新检索）",
            content,
        )
