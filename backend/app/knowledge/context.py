"""Revalidate sources from selected successful conversation history for a new Run."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.errors import ConflictError
from app.execution.models import Run
from app.knowledge.models import RunKnowledgeEvidence

if TYPE_CHECKING:
    from app.knowledge.employee import EmployeeKnowledgeService

LINK = re.compile(r"\[([^\]]*)\]\(([^\s)]+)\)")


class KnowledgeContext:
    def __init__(self, employee: EmployeeKnowledgeService):
        self.employee = employee

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

    def capture(
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
                if evidence is None or self.employee.hit(evidence)["source_url"] != url:
                    continue
                try:
                    self.employee.assert_evidence(db, evidence, allowed)
                except ConflictError:
                    continue
                item = {"source_run_id": run_id, **self.employee.hit(evidence)}
                if len(json.dumps([*result, item], ensure_ascii=False).encode()) > min(
                    18000, budget
                ):
                    continue
                result.append(item)
                seen.add(identifier)
                if len(result) >= captured["top_k"]:
                    return result
        return result

    def bind(self, db: Session, row: Run) -> None:
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
                    **self.employee.hit(evidence),
                }
            ):
                raise ConflictError("knowledge_source_changed", "历史知识来源已变化，请重新发送。")
            self.employee.assert_evidence(db, evidence, allowed)
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
    def clean(content: str, evidence: list[dict]) -> str:
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
