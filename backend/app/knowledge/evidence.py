"""Knowledge evidence owner, independent of SDK tool registration."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ConflictError, InvalidInputError, NotFoundError
from app.execution.contracts import ToolOutcome
from app.execution.models import Run
from app.knowledge.contracts import Chunk
from app.knowledge.models import (
    LibraryChunk,
    LibraryDocument,
    RunKnowledgeEvidence,
)
from app.knowledge.schemas import (
    KnowledgeReadInput,
)
from app.values import digest

if TYPE_CHECKING:
    from app.knowledge.service import KnowledgeService


LINK = re.compile(r"\[([^\]]*)\]\(([^\s)]+)\)")


class KnowledgeEvidence:
    def __init__(self, knowledge: KnowledgeService) -> None:
        self.knowledge = knowledge

    @staticmethod
    def context_revision(db: Session, captured: dict) -> str:
        """Invalidate SDK memory conservatively when its knowledge authority changes."""
        ids = [item["id"] for item in captured["libraries"]]
        versions = list(
            db.execute(
                select(LibraryDocument.id, LibraryDocument.updated_at, LibraryDocument.content_hash)
                .where(LibraryDocument.knowledge_base_id.in_(ids))
                .order_by(LibraryDocument.id)
            )
        )
        return digest(
            [captured["revision"], ids, [[str(value) for value in row] for row in versions]]
        )

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
            self.knowledge.access.run_scope(db, run_id)
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
        """Normalize exact evidence links and verify them in one authorized transaction."""
        if db is None:
            with self.knowledge.database.transaction() as session:
                return self.finalize_answer(run_id, text, session)
        self.knowledge.access.run_scope(db, run_id)
        by_id = {
            item.evidence_id: self.hit(item)["source_url"]
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

        # Exact registered pairs are the authority; do not infer arbitrary source URLs.
        text = re.sub(r"\[(K-[a-f0-9]{16})\]\((knowledge/[^\s)]+)\)", restore_slash, text)
        ids, urls = set(by_id), set(by_id.values())
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
        return text

    @staticmethod
    def source_run(db: Session, run_id: str, captured: dict) -> Run | None:
        row = db.get(Run, run_id)
        if (
            row is None
            or row.status != "succeeded"
            or row.origin_kind != "conversation"
            or row.agent_id != captured["agent_id"]
            or row.owner_user_id != captured["user_id"]
            or row.initiated_by_user_id != captured["user_id"]
        ):
            return None
        return row

    def capture_history(
        self, db: Session, captured: dict, history: list[tuple[str, str]], budget: int
    ) -> list[dict]:
        """The host supplies only successful replies actually selected in this conversation."""
        result: list[dict] = []
        seen: set[str] = set()
        allowed = {item["id"] for item in captured["libraries"]}
        for run_id, content in reversed(history):
            if self.source_run(db, run_id, captured) is None:
                continue
            for identifier, url in LINK.findall(content):
                if identifier in seen:
                    continue
                evidence = db.get(RunKnowledgeEvidence, (run_id, identifier))
                if evidence is None or self.hit(evidence)["source_url"] != url:
                    continue
                try:
                    self.assert_evidence(db, evidence, allowed)
                except ConflictError:
                    continue
                item = {"source_run_id": run_id, **self.hit(evidence)}
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
        """Register only the frozen, previously selected references before accepting the Run."""
        captured = row.config_snapshot.get("knowledge", {})
        allowed = {item["id"] for item in captured.get("libraries", [])}
        for item in captured.get("history_evidence", []):
            source = self.source_run(db, item["source_run_id"], captured)
            evidence = db.get(RunKnowledgeEvidence, (item["source_run_id"], item["evidence_id"]))
            if (
                source is None
                or evidence is None
                or item
                != {
                    "source_run_id": source.id,
                    **self.hit(evidence),
                }
            ):
                raise ConflictError("knowledge_source_changed", "历史知识来源已变化，请重新发送。")
            self.assert_evidence(db, evidence, allowed)
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
        """Remove citation authority only from the input copy; never alter saved history."""
        urls = {item["evidence_id"]: item["source_url"] for item in evidence}

        def replace(match: re.Match[str]) -> str:
            label, target = match.groups()
            internal = target.startswith(
                ("/knowledge/", "knowledge/", "./knowledge/")
            ) or re.search(r"/knowledge/[0-9a-fA-F-]{36}/documents/", target)
            if internal and urls.get(label) != target:
                return "（历史知识来源未纳入本轮，请重新检索）"
            return match.group()

        content = LINK.sub(replace, content)
        return re.sub(
            r"\bK-[a-zA-Z0-9_-]+",
            lambda match: match.group() if match.group() in urls else "历史证据（需重新检索）",
            content,
        )
