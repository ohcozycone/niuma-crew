"""Worker-facing persistence. No HTTP identities or provider objects cross this boundary."""

import json
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_resource_access
from app.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.execution.contracts import (
    SUPPORTED_SNAPSHOT_VERSIONS,
    Completion,
    ContentUpdate,
    InputMessage,
    ToolInvocation,
    ToolPermit,
)
from app.execution.errors import ExecutionFailure
from app.execution.evidence import document
from app.execution.models import ACTIVE, TERMINAL, Run, RunAction
from app.files.models import StoredFile
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.values import utc_now


class RunStore:
    def __init__(self, database: Database, *, files: Any = None) -> None:
        self.files = files
        self.database = database

    def save_evidence(self, id: str, key: str, direction: str, evidence: dict) -> None:
        """Attach immutable bytes and their action reference in one short transaction."""
        if direction not in ("request", "response") or self.files is None:
            raise ValueError("执行证据保存入口未正确配置。")
        prepared = self.files.prepare(
            f"{direction}.json", json.dumps(evidence, ensure_ascii=False, default=str).encode()
        )
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status not in ("running", "cancelling"):
                raise ExecutionFailure("runtime_interrupted")
            action = db.scalar(
                select(RunAction).where(RunAction.run_id == id, RunAction.action_key == key)
            )
            if action is None:
                raise ExecutionFailure("runtime_interrupted")
            file = self.files.register(
                db, row.owner_user_id, prepared, purpose="evidence", run_id=id
            )
            setattr(action, direction + "_file_id", file.id)
            row.revision += 1
            row.actions_revision += 1

    def recover(self, resume: bool = False) -> list[Completion]:
        terminal = []
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            for row in db.scalars(select(Run).where(Run.status.in_(ACTIVE))):
                if row.status == "cancelling":
                    terminal.append(Completion(row.id, None, "cancelled"))
                elif (
                    resume
                    and row.config_snapshot.get("schema_version") in SUPPORTED_SNAPSHOT_VERSIONS
                    and row.config_snapshot.get("checkpoint_resumable", False)
                ):
                    row.status = "queued"
                    self._close_actions(db, row, "interrupted", "runtime_interrupted")
                    row.revision += 1
                else:
                    terminal.append(Completion(row.id, None, "interrupted", "runtime_interrupted"))
        return terminal

    @staticmethod
    def record_history(db: Session, run: Run) -> None:
        evidence = run.config_snapshot.get("knowledge", {}).get("history_evidence", [])
        if evidence:
            now = utc_now()
            db.add(
                RunAction(
                    run_id=run.id,
                    sequence=1,
                    action_key="knowledge:history",
                    kind="knowledge",
                    status="succeeded",
                    safe_details={
                        "operation": "history_reuse",
                        "source_count": len(evidence),
                        "sources": [
                            {
                                "title": item["title"],
                                "url": item["source_url"],
                                "status": "succeeded",
                            }
                            for item in evidence
                        ],
                    },
                    started_at=now,
                    finished_at=now,
                )
            )
            run.actions_revision += 1

    def load(self, id: str) -> tuple[Run, list[InputMessage]]:
        with self.database.transaction() as db:
            row = require_run(db, id)
            return row, row.input_snapshot

    def queued_metadata(self) -> list[tuple[str, datetime | None]]:
        with self.database.transaction() as db:
            return [
                (row.id, row.created_at if row.started_at is None else None)
                for row in db.scalars(
                    select(Run).where(Run.status == "queued").order_by(Run.created_at, Run.id)
                )
            ]

    def claim(self, id: str) -> bool:
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status != "queued":
                return False
            row.status, row.started_at = "running", row.started_at or utc_now()
            row.revision += 1
            return True

    def checkpoint_saved(self, id: str, checkpoint_id: str) -> None:
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status in ACTIVE:
                row.checkpoint_id = checkpoint_id

    def restore_control(self, id: str) -> dict[str, Any]:
        with self.database.transaction() as db:
            row = require_run(db, id)
            steps = list(db.scalars(select(RunAction).where(RunAction.run_id == id)))
            return {
                "active_skills": {
                    step.skill_id
                    for step in steps
                    if step.kind == "skill_activation" and step.status == "succeeded"
                },
                "contents": [
                    ContentUpdate(
                        step.action_key,
                        step.output_text,
                        step.reasoning_text,
                        step.reasoning_truncated,
                        step.safe_details.get("has_tool_calls", False),
                    )
                    for step in steps
                    if step.kind == "model_call"
                ],
                "usage": row.usage if row.started_at else None,
            }

    def state(self, id: str) -> tuple[str, str | None]:
        with self.database.transaction() as db:
            row = require_run(db, id)
            return row.status, row.initiated_by_session_id

    def active_ids(self) -> list[str]:
        with self.database.transaction() as db:
            return list(db.scalars(select(Run.id).where(Run.status.in_(ACTIVE))))

    @classmethod
    def finish(cls, db: Session, row: Run, intent: Completion) -> None:
        if intent.status not in TERMINAL:
            raise ValueError("Invalid terminal execution status")
        cls._write_progress(db, row, intent.progress)
        unfinished = cls._close_actions(
            db,
            row,
            "interrupted"
            if intent.status == "interrupted"
            else "cancelled"
            if intent.status == "cancelled"
            else "failed",
            intent.error,
        )
        row.status, row.error_code, row.finished_at = intent.status, intent.error, utc_now()
        if intent.usage is not None and not unfinished:
            row.usage = intent.usage
        row.revision += 1

    @staticmethod
    def _close_actions(db: Session, row: Run, status: str, error: str | None) -> bool:
        unfinished_model = False
        changed = False
        for step in db.scalars(
            select(RunAction).where(RunAction.run_id == row.id, RunAction.status == "running")
        ):
            changed = True
            if step.kind == "model_call":
                unfinished_model = True
                # An unfinished request may have consumed tokens without reporting usage.
                row.usage = {
                    key: None
                    for key in (
                        "input_tokens",
                        "output_tokens",
                        "total_tokens",
                        "cached_input_tokens",
                        "reasoning_tokens",
                    )
                }
            actual = "unknown" if step.kind in ("model_call", "tool_call") else status
            step.status, step.error_code, step.finished_at = actual, error, utc_now()
        if changed:
            row.actions_revision += 1
        return unfinished_model

    @staticmethod
    def _set_content(step: Any, content: ContentUpdate) -> None:
        step.output_text = content.output_text
        step.reasoning_text = content.reasoning_text
        step.reasoning_truncated = content.reasoning_truncated
        step.safe_details = {**step.safe_details, "has_tool_calls": content.has_tool_calls}

    @classmethod
    def _write_progress(cls, db: Session, row: Run, contents: Iterable[ContentUpdate]) -> bool:
        changed = False
        for content in contents:
            step = db.scalar(
                select(RunAction).where(
                    RunAction.run_id == row.id, RunAction.action_key == content.key
                )
            )
            if step and step.status == "running":
                cls._set_content(step, content)
                changed = True
        return changed

    def update_progress(self, id: str, contents: list[ContentUpdate]) -> None:
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status == "running" and self._write_progress(db, row, contents):
                row.revision += 1

    def start_action(
        self,
        id: str,
        key: str,
        kind: str,
        details: dict[str, Any] | None = None,
        skill_id: str | None = None,
        *,
        budget: str | None = None,
        authorize: Callable[[Session], Any] | None = None,
    ) -> str:
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if authorize:
                authorize(db)
            if budget:
                self._reserve(row, budget)
            return self._start_action(db, row, key, kind, details, skill_id)

    @staticmethod
    def _reserve(row: Run, counter: str) -> int:
        limit = {
            "model_calls": "max_model_calls",
            "skill_reads": "max_skill_reads",
            "tool_calls": "max_tool_calls",
        }[counter]
        count = int(getattr(row, counter)) + 1
        if count > row.config_snapshot[limit]:
            raise ExecutionFailure("agent_budget_exceeded")
        setattr(row, counter, count)
        return count

    def start_model(self, id: str, authorize: Callable[[Session], Any]) -> tuple[int, str]:
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            authorize(db)
            number = self._reserve(row, "model_calls")
            key = f"model:{number}"
            return number, self._start_action(db, row, key, "model_call", {"round": number})

    def _start_action(
        self,
        db: Session,
        row: Run,
        key: str,
        kind: str,
        details: dict[str, Any] | None = None,
        skill_id: str | None = None,
    ) -> str:
        id = row.id
        if row.status != "running":
            raise ConflictError("runtime_interrupted", "执行已停止。")
        existing = db.scalar(
            select(RunAction)
            .where(RunAction.run_id == id, RunAction.call_key == key)
            .order_by(RunAction.sequence.desc())
            .limit(1)
        )
        retry_read = (details or {}).get("recovery") == "readonly"
        if existing and not (kind == "tool_call" and retry_read):
            raise ConflictError("runtime_interrupted", "Action already recorded")
        if skill_id and skill_id not in row.config_snapshot.get("authorized_skill_ids", []):
            raise PermissionDeniedError("skill_not_allowed", "Skill is not authorized")
        sequence = (
            db.scalar(select(func.max(RunAction.sequence)).where(RunAction.run_id == id)) or 0
        ) + 1
        db.add(
            RunAction(
                run_id=id,
                sequence=sequence,
                action_key=key if existing is None else f"{key}:attempt:{sequence}",
                call_key=key,
                parent_action_id=self._parent_action(db, id, key),
                kind=kind,
                skill_id=skill_id,
                safe_details=details or {},
                started_at=utc_now(),
            )
        )
        row.revision += 1
        row.actions_revision += 1
        return key if existing is None else f"{key}:attempt:{sequence}"

    @staticmethod
    def _parent_action(db: Session, id: str, key: str) -> str | None:
        tool_id = key.removeprefix("tool:")
        for item in db.scalars(
            select(RunAction)
            .where(RunAction.run_id == id, RunAction.kind == "model_call")
            .order_by(RunAction.sequence.desc())
        ):
            if tool_id in item.safe_details.get("tool_call_ids", []):
                return item.id
        return None

    def finish_action(
        self,
        id: str,
        key: str,
        status: str = "succeeded",
        error: str | None = None,
        details: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        content: ContentUpdate | None = None,
        *,
        result_payload: dict[str, Any] | None = None,
    ) -> None:
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status not in ("running", "cancelling"):
                raise ConflictError("runtime_interrupted", "执行已停止。")
            step = db.scalar(
                select(RunAction).where(RunAction.run_id == id, RunAction.action_key == key)
            )
            if (
                step
                and step.status == "succeeded"
                and status == "succeeded"
                and step.kind in ("tool_call", "skill_activation")
            ):
                return
            if not step or step.status != "running":
                raise ConflictError("runtime_interrupted", "步骤已结束，不覆盖记录。")
            # Cancelling the Run does not erase an already confirmed action outcome.
            # The terminal Run decision still prevents delivery and new actions.
            step.status, step.error_code, step.finished_at = status, error, utc_now()
            if details:
                step.safe_details = {**step.safe_details, **details}
            if content is not None:
                self._set_content(step, content)
            if usage is not None:
                row.usage = usage
            if result_payload is not None:
                step.result_payload = result_payload
                step.result_ref = "action:" + step.id
            row.revision += 1
            row.actions_revision += 1

    def begin_tool(
        self, id: str, invocation: ToolInvocation, authorize: Callable[[Session], Any]
    ) -> ToolPermit:
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status != "running":
                raise ExecutionFailure("runtime_interrupted")
            binding = authorize(db)
            prior = db.scalar(
                select(RunAction)
                .where(RunAction.run_id == id, RunAction.call_key == invocation.key)
                .order_by(RunAction.sequence.desc())
                .limit(1)
            )
            if prior is not None:
                if prior.safe_details.get("fingerprint") != invocation.fingerprint:
                    raise ExecutionFailure("runtime_interrupted")
                if (
                    binding.get("recovery") == "readonly"
                    and prior.status == "succeeded"
                    and prior.result_payload is not None
                ):
                    return ToolPermit(
                        prior.action_key, invocation.fingerprint, prior.result_payload
                    )
                if binding.get("recovery") != "readonly":
                    raise ExecutionFailure("tool_result_unknown")
            count = sum(
                1
                for action in db.scalars(
                    select(RunAction).where(RunAction.run_id == id, RunAction.kind == "tool_call")
                )
                if action.safe_details.get("binding_id") == invocation.binding_id
                and action.safe_details.get("executed") is not False
            )
            if count >= binding["scope_policy"].get("max_calls", 32):
                raise ExecutionFailure("agent_budget_exceeded")
            self._reserve(row, "tool_calls")
            if invocation.skill_id:
                self._reserve(row, "skill_reads")
            details = {
                "tool": binding.get("tool_name", invocation.name),
                "model_tool": invocation.name,
                "name": binding.get("tool_name", invocation.name),
                "binding_id": invocation.binding_id,
                "fingerprint": invocation.fingerprint,
                "recovery": binding.get("recovery", "never"),
            }
            key = self._start_action(
                db, row, invocation.key, "tool_call", details, invocation.skill_id
            )
            return ToolPermit(key, invocation.fingerprint)

    def reject_tool(self, id: str, invocation: ToolInvocation, error: str) -> None:
        """Record a denied request without consuming a tool budget or invoking it."""
        prepared = (
            self.files.prepare(
                "tool-request.json",
                json.dumps(
                    document(
                        "tool_request",
                        {
                            "name": invocation.name,
                            "requested_arguments": invocation.arguments,
                            "authorization_status": "denied",
                            "error_code": error,
                        },
                    ),
                    ensure_ascii=False,
                ).encode(),
            )
            if self.files
            else None
        )
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status != "running":
                return
            if db.scalar(
                select(RunAction.id).where(
                    RunAction.run_id == id, RunAction.call_key == invocation.key
                )
            ):
                return
            self._start_action(
                db,
                row,
                invocation.key,
                "tool_call",
                {
                    "tool": invocation.name,
                    "binding_id": invocation.binding_id,
                    "authorization_status": "denied",
                    "executed": False,
                },
            )
            db.flush()
            action = db.scalar(
                select(RunAction).where(
                    RunAction.run_id == id, RunAction.action_key == invocation.key
                )
            )
            assert action is not None
            action.status, action.error_code, action.finished_at = "failed", error, utc_now()
            if prepared:
                file = self.files.register(
                    db, row.owner_user_id, prepared, purpose="evidence", run_id=id
                )
                action.request_file_id = file.id


def require_run(db: Session, id: str, actor: Actor | None = None) -> Run:
    row = db.get(Run, id)
    if not row:
        raise NotFoundError("run_not_found", "执行记录不存在。")
    if actor:
        require_resource_access(actor, row.owner_user_id)
    return row


def retained_file_ids(db: Session, candidates: list[StoredFile]) -> set[str]:
    """Retain accepted inputs and durable output references independently of messages."""
    ids = {row.id for row in candidates}
    origins = {row.origin_run_id for row in candidates if row.origin_run_id}
    retained: set[str] = set()
    for request_id, response_id in db.execute(
        select(RunAction.request_file_id, RunAction.response_file_id).where(
            RunAction.run_id.in_(origins)
        )
    ):
        retained.update(value for value in (request_id, response_id) if value in ids)
    active = set(db.scalars(select(Run.id).where(Run.id.in_(origins), Run.status.in_(ACTIVE))))
    retained.update(row.id for row in candidates if row.origin_run_id in active)
    for record in db.execute(
        select(Run.config_snapshot, Run.result_data).execution_options(yield_per=128)
    ):
        snapshot = cast(dict, record[0])
        result = cast(dict | None, record[1])
        refs = [*snapshot.get("input_files", []), *(result or {}).get("output_files", [])]
        retained.update(ref["id"] for ref in refs if ref["id"] in ids)
    details: dict
    for details in db.scalars(
        select(RunAction.safe_details).where(
            RunAction.run_id.in_(origins), RunAction.kind == "tool_call"
        )
    ):
        if details.get("result_file_id") in ids:
            retained.add(details["result_file_id"])
        retained.update(
            source["file_id"]
            for source in cast(list[dict], details.get("sources", []))
            if source.get("file_id") in ids
        )
    return retained & ids
