import logging

from sqlalchemy import select

from app.auth.work_authorizations import authorize_work
from app.errors import (
    ConflictError,
    RateLimitError,
    ServiceError,
    ServiceUnavailableError,
)
from app.evaluations.acceptance import finish_batch, record_result
from app.evaluations.models import BATCH_ACTIVE, EvaluationBatch, EvaluationCase
from app.execution.queries import optional_run
from app.execution.service import RunService
from app.infrastructure.database.identifiers import allocate_id
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.runtime.contracts.runs import ACTIVE, run_thread_id
from app.values import digest, utc_now

logger = logging.getLogger(__name__)


class EvaluationProgression:
    def __init__(self, database: Database, runs: RunService):
        self.database, self.runs = database, runs

    def sweep(self) -> None:
        with self.database.transaction() as db:
            ids = list(
                db.scalars(
                    select(EvaluationBatch.id)
                    .where(EvaluationBatch.status.in_(BATCH_ACTIVE))
                    .order_by(EvaluationBatch.created_at)
                    .limit(32)
                )
            )
        for batch_id in ids:
            try:
                self.advance(batch_id)
            except Exception as error:
                # 每个考核独立推进和回滚，避免一项故障阻塞其他考核。
                logger.warning(
                    "evaluation.advance_failed batch=%s type=%s", batch_id, type(error).__name__
                )

    def advance(self, batch_id: str) -> None:
        """每次只推进一步；执行受理与题目绑定一起提交。"""
        with self.database.transaction() as db:
            reserve_writer(db, EvaluationBatch.__table__)
            batch = db.get(EvaluationBatch, batch_id)
            if batch is None or batch.status not in BATCH_ACTIVE:
                return
            case = db.scalar(
                select(EvaluationCase)
                .where(
                    EvaluationCase.batch_id == batch.id,
                    EvaluationCase.status.in_(("pending", "running")),
                )
                .order_by(EvaluationCase.ordinal)
                .limit(1)
            )
            if case is None:
                finish_batch(db, batch)
                return
            if case.run_id:
                run = optional_run(db, case.run_id)
                if run.status in ACTIVE:
                    return
                if batch.status == "cancelling":
                    case.answer, case.finished_at, case.status = (
                        run.result_text,
                        utc_now(),
                        "cancelled",
                    )
                else:
                    record_result(batch, case, run)
                db.flush()
                finish_batch(db, batch)
                return
            if batch.status == "cancelling":
                case.status, case.finished_at = "cancelled", utc_now()
                db.flush()
                finish_batch(db, batch)
                return
            try:
                actor = authorize_work(db, batch.owner_user_id, batch.session_id)
                snapshot, _ = self.runs.configuration.prepare(
                    db, batch.agent_id, case.prompt, [], tools_enabled=False
                )
                if digest(snapshot) != batch.configuration_hash:
                    raise ConflictError("evaluation_config_changed", "员工考核配置已改变。")
                run = self.runs.submit(
                    db,
                    actor,
                    owner_user_id=batch.owner_user_id,
                    agent_id=batch.agent_id,
                    content=case.prompt,
                    input_message_id=allocate_id(db),
                    selected_skill_ids=[],
                    file_ids=[],
                    origin_kind="evaluation",
                    operation="evaluation.case",
                    request_id=case.id,
                    digest=digest([batch.id, case.id, case.prompt]),
                    thread_id=run_thread_id("evaluation", case.id),
                    tools_enabled=False,
                )
            except (RateLimitError, ServiceUnavailableError):
                return
            except ServiceError as error:
                batch.error_code = error.code
                for pending in db.scalars(
                    select(EvaluationCase).where(
                        EvaluationCase.batch_id == batch.id, EvaluationCase.status == "pending"
                    )
                ):
                    pending.status, pending.error_code, pending.finished_at = (
                        "error",
                        error.code,
                        utc_now(),
                    )
                db.flush()
                finish_batch(db, batch)
                return
            case.run_id, case.status = run.id, "running"
            batch.status, batch.started_at = "running", batch.started_at or utc_now()
