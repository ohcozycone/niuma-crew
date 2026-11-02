"""Execution admission participates in the caller's business transaction."""

import hashlib
import json
from copy import deepcopy

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent_runtime.contracts import InputMessage
from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.errors import ConflictError, RateLimitError, ServiceUnavailableError
from app.execution.config import RuntimeConfig
from app.execution.contracts import ExecutionStatus, RunSpec
from app.execution.models import ACTIVE, Run


def request_digest(command: dict) -> str:
    return hashlib.sha256(
        json.dumps(command, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class RunAdmission:
    def __init__(self, settings: RuntimeConfig, status: ExecutionStatus) -> None:
        self.settings, self.status = settings, status

    def replay(
        self, db: Session, actor: Actor, operation: str, key: str, digest: str
    ) -> Run | None:
        row = db.scalar(
            select(Run).where(
                Run.initiated_by_user_id == actor.user_id,
                Run.operation == operation,
                Run.client_request_id == key,
            )
        )
        if row and row.request_hash != digest:
            raise ConflictError("idempotency_conflict", "这个请求标识已用于其他内容。")
        return row

    def check_capacity(self, db: Session, actor: Actor) -> None:
        require_permission(actor, "runs:create")
        if not self.status.accepting:
            raise ServiceUnavailableError(
                "runtime_unavailable", "执行服务暂时不可用，请稍后重试。", retry_after=1
            )
        active = db.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.initiated_by_user_id == actor.user_id, Run.status.in_(ACTIVE))
        )
        queued = db.scalar(select(func.count()).select_from(Run).where(Run.status == "queued"))
        active = active or 0
        queued = queued or 0
        if active >= self.settings.per_user_capacity or queued >= self.settings.queue_capacity:
            raise RateLimitError(
                "run_capacity_exceeded", "执行名额已满，请稍后重试。", retry_after=2
            )

    def accept(
        self,
        db: Session,
        actor: Actor,
        *,
        owner_user_id: str,
        agent_id: str,
        origin_kind: str,
        operation: str,
        request_id: str,
        digest: str,
        snapshot: RunSpec,
        messages: list[InputMessage],
        retry_of: Run | None = None,
    ) -> Run:
        if not messages or messages[-1]["role"] != "user":
            raise ValueError("执行输入必须包含用户工作输入。")
        if retry_of and (
            retry_of.owner_user_id != owner_user_id
            or retry_of.agent_id != agent_id
            or retry_of.origin_kind != origin_kind
        ):
            raise ConflictError("retry_not_allowed", "重试来源不一致。")
        row = Run(
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
            input_snapshot=deepcopy(messages),
        )
        db.add(row)
        db.flush()
        return row
