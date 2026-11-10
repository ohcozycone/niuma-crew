from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.errors import (
    CodedFailure,
    ConflictError,
    InvalidInputError,
    RateLimitError,
    ServiceError,
    ServiceUnavailableError,
)
from app.execution.authorization import authorize_run
from app.execution.config import RuntimeConfig
from app.execution.errors import (
    PersistenceFailure,
    terminal_status,
)
from app.execution.models import ACTIVE, Run, RunAction
from app.execution.store import RunStore, require_run
from app.infrastructure.database.identifiers import allocate_id
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.runtime.contracts.runs import (
    RUN_SNAPSHOT_VERSION,
    Completion,
    ExecutionStatus,
    run_thread_id,
)
from app.runtime.contracts.tools import ModelExposure, ToolInvocation
from app.values import utc_now

if TYPE_CHECKING:
    from app.knowledge.service import KnowledgeService
    from app.model_connections.service import ModelConnectionService


def request_digest(command: dict) -> str:
    return hashlib.sha256(
        json.dumps(command, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def find_request(
    db: Session, actor: Actor, operation: str, key: str, digest: str | None = None
) -> Run | None:
    """先查幂等原请求，再检查新工作的准入条件。"""
    require_permission(actor, "runs:create")
    row = db.scalar(
        select(Run).where(
            Run.initiated_by_user_id == actor.user_id,
            Run.operation == operation,
            Run.client_request_id == key,
        )
    )
    if row is not None:
        if digest is not None and row.request_hash != digest:
            raise ConflictError("idempotency_conflict")
        return require_run(db, row.id, actor)
    return None


def active_run_ids(database: Database) -> list[str]:
    with database.transaction() as db:
        return list(db.scalars(select(Run.id).where(Run.status.in_(ACTIVE))))


class RunService:
    def __init__(
        self,
        database: Database,
        settings: RuntimeConfig,
        status: ExecutionStatus,
        configuration: Any,
        connections: ModelConnectionService,
        *,
        check_outputs: Callable,
        knowledge: KnowledgeService | None = None,
        prepare_content: Callable | None = None,
    ) -> None:
        self.database, self.settings, self.status = database, settings, status
        self.configuration = configuration
        self._connections, self._knowledge = connections, knowledge
        self.check_outputs, self.prepare_content = check_outputs, prepare_content

    def authorize(
        self,
        row: Run,
        active: Iterable[str] = (),
        db: Session | None = None,
        invocation: ToolInvocation | None = None,
        *,
        exposure: ModelExposure | None = None,
    ) -> Any:
        """复用调用方事务检查授权；未传入时新建短事务。"""
        if db is None:
            with self.database.transaction() as session:
                return self.authorize(row, active, session, invocation, exposure=exposure)
        return authorize_run(
            db,
            row,
            active,
            invocation,
            connections=self._connections,
            knowledge=self._knowledge,
            exposed_tool_ids=exposure["exposed_tool_ids"] if exposure else (),
        )

    def submit(
        self,
        db: Session,
        actor: Actor,
        *,
        owner_user_id: str,
        agent_id: str,
        content: str,
        input_message_id: str,
        selected_skill_ids: list[str],
        file_ids: list[str],
        origin_kind: str,
        operation: str,
        request_id: str,
        digest: str,
        thread_id: str,
        base_run_id: str | None = None,
        retry_of: Run | None = None,
        allowed_file_ids: set[str] | None = None,
        tools_enabled: bool = True,
    ) -> Run:
        """在调用方事务中冻结输入并创建排队记录。"""
        if row := find_request(db, actor, operation, request_id, digest):
            return row
        if not self.status.accepting:
            raise ServiceUnavailableError("runtime_unavailable", retry_after=1)
        active = (
            db.scalar(
                select(func.count())
                .select_from(Run)
                .where(Run.initiated_by_user_id == actor.user_id, Run.status.in_(ACTIVE))
            )
            or 0
        )
        queued = db.scalar(select(func.count()).select_from(Run).where(Run.status == "queued")) or 0
        if active >= self.settings.per_user_capacity or queued >= self.settings.queue_capacity:
            raise RateLimitError("run_capacity_exceeded", retry_after=2)
        if not thread_id or not content.strip():
            raise InvalidInputError("input_required")
        if retry_of and (
            retry_of.owner_user_id != owner_user_id
            or retry_of.agent_id != agent_id
            or retry_of.origin_kind != origin_kind
        ):
            raise ConflictError("retry_not_allowed")
        base = require_run(db, base_run_id, actor) if base_run_id else None
        base_version = base.config_snapshot.get("schema_version") if base else RUN_SNAPSHOT_VERSION
        if type(base_version) is not int or not 1 <= base_version <= RUN_SNAPSHOT_VERSION:
            raise ConflictError("checkpoint_unavailable")
        reset_version = base_version < RUN_SNAPSHOT_VERSION
        expected_thread = thread_id
        if reset_version:
            prefix = f"{origin_kind}:v{RUN_SNAPSHOT_VERSION}:"
            if not thread_id.startswith(prefix):
                raise ConflictError("checkpoint_unavailable")
            expected_thread = run_thread_id(
                origin_kind, thread_id.removeprefix(prefix), snapshot_version=base_version
            )
        if base and (
            base.owner_user_id != owner_user_id
            or base.agent_id != agent_id
            or base.origin_kind != origin_kind
            or base.status != "succeeded"
            or base.thread_id != expected_thread
            or not base.checkpoint_id
        ):
            raise ConflictError("checkpoint_unavailable")
        if reset_version:
            base = None
        snapshot, size = self.configuration.prepare(
            db,
            agent_id,
            content,
            selected_skill_ids,
            tools_enabled=tools_enabled,
        )
        snapshot["memory_reset"] = reset_version
        if base:
            snapshot["memory_reset"] = self.configuration.invalidates_memory(
                base.config_snapshot, snapshot
            )
        if file_ids:
            size += self.configuration.capture_files(
                db, snapshot, file_ids, owner_user_id, allowed_ids=allowed_file_ids
            )
        if size > snapshot["context_bytes"]:
            raise InvalidInputError("context_limit_exceeded")
        # 引用资格独立于框架对话记忆核验。
        self.configuration.capture_evidence(
            db,
            snapshot,
            [(base.id, base.result_text)] if base and base.result_text else [],
            size,
            owner_user_id=owner_user_id,
            thread_id=thread_id,
        )
        row = Run(
            id=allocate_id(db),
            thread_id=thread_id,
            base_checkpoint_id=base.checkpoint_id if base else None,
            base_run_id=base.id if base else None,
            agent_id=agent_id,
            owner_user_id=owner_user_id,
            initiated_by_user_id=actor.user_id,
            initiated_by_session_id=actor.session_id,
            origin_kind=origin_kind,
            operation=operation,
            trigger="retry" if retry_of else "user",
            mode="execute",
            client_request_id=request_id,
            request_hash=digest,
            retry_of_run_id=retry_of.id if retry_of else None,
            model_connection_id=snapshot["connection_id"],
            config_snapshot=deepcopy(snapshot),
            input_snapshot=[{"id": input_message_id, "role": "user", "content": content}],
        )
        db.add(row)
        db.flush()
        if snapshot.get("knowledge"):
            self.configuration.bind_history(db, row)
            RunStore.record_history(db, row)
        return row

    @staticmethod
    def cancel(db: Session, row: Run) -> None:
        """登记取消，不提交调用方事务。"""
        if row.status not in ("queued", "running"):
            return
        row.cancel_requested_at = utc_now()
        if row.status == "queued":
            RunStore.finish(db, row, Completion(row.id, None, "cancelled"))
        else:
            row.status = "cancelling"
            row.revision += 1
        db.flush()

    def complete(self, intent: Completion) -> None:
        """原子保存已核验成果与 Run 终态。"""
        try:
            with self.database.transaction() as db:
                reserve_writer(db, Run.__table__)
                row = require_run(db, intent.run_id)
                if row.status not in ACTIVE:
                    return
                if row.status == "cancelling":
                    intent = replace(
                        intent, status="cancelled", content=None, error=None, structured=None
                    )
                if intent.status == "succeeded":
                    try:
                        self.authorize(row, db=db)
                        if self.prepare_content is not None and intent.content:
                            intent = replace(
                                intent, content=self.prepare_content(db, row, intent.content)
                            )
                        if not intent.content or not intent.content.strip():
                            raise InvalidInputError("empty_response")
                        if len(intent.content.encode()) > row.config_snapshot["max_output_bytes"]:
                            raise InvalidInputError("output_limit_exceeded")
                        self._check_outputs(db, row, intent)
                    # 持久化故障保留协调重试，不转成业务拒绝。
                    except PersistenceFailure:
                        raise
                    except (CodedFailure, ServiceError) as error:
                        code = error.code
                        intent = replace(
                            intent,
                            status=terminal_status(code),
                            error=code,
                            content=None,
                            structured=None,
                        )
                if intent.status != "succeeded" and not row.config_snapshot.get(
                    "allow_partial_output", True
                ):
                    intent = replace(intent, content=None, structured=None)
                if (
                    intent.content
                    and len(intent.content.encode()) > row.config_snapshot["max_output_bytes"]
                ):
                    raise ValueError("Execution result exceeds the accepted output limit")
                row.result_text = intent.content
                row.result_data = dict(intent.structured) if intent.structured is not None else None
                RunStore.finish(db, row, intent)
        except PersistenceFailure:
            raise
        except Exception as error:
            raise PersistenceFailure() from error

    def _check_outputs(self, db: Session, row: Run, intent: Completion) -> None:
        if db.scalar(
            select(RunAction.id)
            .where(
                RunAction.run_id == row.id,
                RunAction.kind == "tool_call",
                RunAction.status == "running",
            )
            .limit(1)
        ):
            raise InvalidInputError("tool_result_unknown")
        self.check_outputs(
            db,
            row.id,
            row.owner_user_id,
            list(intent.structured["output_files"]) if intent.structured else [],
        )
