"""Accept and complete executions using explicit, short application transactions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.auth.work_authorizations import authorize_work
from app.employees.access import assert_binding, authorize_execution, authorize_tool
from app.errors import (
    AuthenticationError,
    ConflictError,
    InvalidInputError,
    PermissionDeniedError,
    RateLimitError,
    ServiceUnavailableError,
)
from app.execution.config import RuntimeConfig
from app.execution.contracts import (
    RUN_SNAPSHOT_VERSION,
    Completion,
    ExecutionStatus,
    ToolInvocation,
)
from app.execution.errors import (
    ERROR_MESSAGES,
    ExecutionFailure,
    PersistenceFailure,
    terminal_status,
)
from app.execution.models import ACTIVE, Run, RunAction
from app.execution.store import RunStore, require_run
from app.infrastructure.database.identifiers import allocate_id
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.values import digest, utc_now

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
    """Look up the original request before any new-work checks or writes."""
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
            raise ConflictError("idempotency_conflict", "这个请求标识已用于其他内容。")
        return require_run(db, row.id, actor)
    return None


def active_run_ids(database: Database) -> list[str]:
    """Return persisted active IDs for resource maintenance, independently of the host."""
    with database.transaction() as db:
        return list(db.scalars(select(Run.id).where(Run.status.in_(ACTIVE))))


class RunService:
    """Own execution admission, cancellation requests and durable completion."""

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
    ) -> Any:
        """Recheck current grants in the supplied transaction or a fresh short one."""
        if db is None:
            with self.database.transaction() as session:
                return self.authorize(row, active, session, invocation)
        try:
            authorize_work(db, row.initiated_by_user_id, row.initiated_by_session_id)
        except (AuthenticationError, PermissionDeniedError) as error:
            raise ExecutionFailure("actor_session_invalid") from error
        used = cast(
            set[str],
            set(
                db.scalars(
                    select(RunAction.skill_id).where(
                        RunAction.run_id == row.id,
                        RunAction.kind == "skill_activation",
                        RunAction.status == "succeeded",
                        RunAction.skill_id.is_not(None),
                    )
                )
            ),
        )
        snapshot = row.config_snapshot
        inherited = (
            require_run(db, row.base_run_id).config_snapshot
            if row.base_run_id and not snapshot.get("memory_reset")
            else {}
        )
        if snapshot.get("knowledge"):
            if self._knowledge is None or snapshot["knowledge"]["user_id"] != row.owner_user_id:
                raise ExecutionFailure("knowledge_access_revoked")
            self._knowledge.access.assert_current(db, snapshot, row.id)
            current_scope = digest(
                [
                    snapshot["agent_id"],
                    snapshot.get("tool_user_id"),
                    self._knowledge.evidence.context_revision(db, snapshot["knowledge"]),
                ]
            )
            if current_scope != snapshot["memory_scope"]:
                raise ExecutionFailure("knowledge_source_changed")
        # Retained thread messages may contain resources not called again in this Run.
        inherited_skills = {skill["skill_id"] for skill in inherited.get("skills", [])}
        authorize_execution(db, snapshot, used | set(active) | inherited_skills)
        self._connections.assert_current(
            snapshot["connection_id"],
            snapshot["connection_config_revision"],
            snapshot["connection_credential_revision"],
            db=db,
        )
        used_tools = {
            action.safe_details.get("binding_id")
            for action in db.scalars(
                select(RunAction).where(RunAction.run_id == row.id, RunAction.kind == "tool_call")
            )
        }
        used_tools.update(binding["binding_id"] for binding in inherited.get("tools", []))
        for binding in snapshot.get("tools", []):
            if binding["binding_id"] in used_tools and binding["kind"] != "knowledge":
                assert_binding(db, snapshot, binding)
        if invocation is not None:
            if invocation.binding_id.startswith("knowledge:"):
                if self._knowledge is None:
                    raise ExecutionFailure("tool_not_allowed")
                return self._knowledge.access.authorize(db, snapshot, invocation)
            return authorize_tool(db, snapshot, invocation)

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
        """Freeze one input and queue its execution in the caller's transaction."""
        if row := find_request(db, actor, operation, request_id, digest):
            return row
        if not self.status.accepting:
            raise ServiceUnavailableError(
                "runtime_unavailable", "执行服务暂时不可用，请稍后重试。", retry_after=1
            )
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
            raise RateLimitError(
                "run_capacity_exceeded", "执行名额已满，请稍后重试。", retry_after=2
            )
        if not thread_id or not content.strip():
            raise InvalidInputError("input_required", "执行线程和输入不能为空。")
        if retry_of and (
            retry_of.owner_user_id != owner_user_id
            or retry_of.agent_id != agent_id
            or retry_of.origin_kind != origin_kind
        ):
            raise ConflictError("retry_not_allowed", "重试来源不一致。")
        base = require_run(db, base_run_id, actor) if base_run_id else None
        if base and (
            base.owner_user_id != owner_user_id
            or base.agent_id != agent_id
            or base.origin_kind != origin_kind
            or base.status != "succeeded"
            or base.thread_id != thread_id
            or not base.checkpoint_id
            or base.config_snapshot.get("schema_version") != RUN_SNAPSHOT_VERSION
        ):
            raise ConflictError("checkpoint_unavailable", "本次交流的执行存档不可续接。")
        snapshot, size = self.configuration.prepare(
            db,
            agent_id,
            content,
            selected_skill_ids,
            actor.user_id,
            tools_enabled=tools_enabled,
        )
        if base:
            snapshot["memory_reset"] = self.configuration.invalidates_memory(
                base.config_snapshot, snapshot
            )
        if snapshot.get("knowledge") and actor.user_id != owner_user_id:
            raise ConflictError(
                "knowledge_owner_mismatch", "个人知识库不能用于他人拥有的对话，请创建自己的对话。"
            )
        if file_ids:
            size += self.configuration.capture_files(
                db, snapshot, file_ids, owner_user_id, allowed_ids=allowed_file_ids
            )
        if size > snapshot["context_bytes"]:
            raise InvalidInputError("context_limit_exceeded", "工作输入超过上下文限制。")
        # Evidence qualification is distinct from the SDK's conversation memory.
        self.configuration.capture_evidence(
            db, snapshot, [(base.id, base.result_text)] if base and base.result_text else [], size
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
        """Request cancellation without committing the caller's transaction."""
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
        """Atomically commit the checked execution output and its terminal state."""
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
                            raise InvalidInputError(
                                "empty_response", ERROR_MESSAGES["empty_response"]
                            )
                        if len(intent.content.encode()) > row.config_snapshot["max_output_bytes"]:
                            raise InvalidInputError(
                                "output_limit_exceeded", ERROR_MESSAGES["output_limit_exceeded"]
                            )
                        self._check_outputs(db, row, intent)
                    except Exception as error:
                        code = getattr(error, "code", None)
                        if not isinstance(code, str):
                            raise
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
            raise PersistenceFailure("执行成果事务未能提交。") from error

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
            raise InvalidInputError(
                "tool_result_unknown", "仍有未确认的工具动作，不能完成本次工作。"
            )
        self.check_outputs(
            db,
            row.id,
            row.owner_user_id,
            list(intent.structured["output_files"]) if intent.structured else [],
        )
