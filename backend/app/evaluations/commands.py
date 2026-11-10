import logging
import random
from copy import deepcopy

from sqlalchemy import func, select

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.auth.work_authorizations import authorize_work
from app.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
)
from app.evaluations.acceptance import finish_batch, record_result
from app.evaluations.benchmark import (
    GRADER_VERSION,
    SUITE_ID,
    exam_prompt,
    load_suite,
)
from app.evaluations.models import BATCH_ACTIVE, EvaluationBatch, EvaluationCase
from app.evaluations.queries import require_batch, summary
from app.execution.queries import optional_run
from app.execution.service import RunService
from app.infrastructure.database.identifiers import allocate_id
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.runtime.contracts.runs import ACTIVE
from app.values import digest, utc_now

logger = logging.getLogger(__name__)


class EvaluationCommands:
    def __init__(self, database: Database, runs: RunService):
        self.database, self.runs = database, runs

    def create(self, actor: Actor, agent_id: str, suite_id: str, count: int, key: str) -> dict:
        require_permission(actor, "runs:create")
        if suite_id != SUITE_ID:
            raise NotFoundError("evaluation_suite_not_found", "所选题库不存在。")
        version, available = load_suite()
        if type(count) is not int or not 1 <= count <= len(available):
            raise InvalidInputError("evaluation_sample_invalid", "题数应在 1 到 400 之间。")
        fingerprint = digest([agent_id, suite_id, count])
        with self.database.transaction() as db:
            reserve_writer(db, EvaluationBatch.__table__)
            existing = db.scalar(
                select(EvaluationBatch).where(
                    EvaluationBatch.owner_user_id == actor.user_id,
                    EvaluationBatch.request_id == key,
                )
            )
            if existing:
                if existing.request_hash != fingerprint:
                    raise ConflictError("evaluation_request_conflict", "提交标识已用于另一项考核。")
                return summary(db, existing)
            authorize_work(db, actor.user_id, actor.session_id)
            if not self.runs.status.accepting:
                raise ServiceUnavailableError("runtime_unavailable", "执行服务暂不可用。")
            if (
                db.scalar(
                    select(func.count())
                    .select_from(EvaluationBatch)
                    .where(
                        EvaluationBatch.owner_user_id == actor.user_id,
                        EvaluationBatch.status.in_(BATCH_ACTIVE),
                    )
                )
                or 0
            ) >= 2:
                raise RateLimitError("evaluation_capacity", "最多同时安排两次未结束考核。")
            snapshot, _ = self.runs.configuration.prepare(
                db, agent_id, "考核配置核对", [], tools_enabled=False
            )
            row = EvaluationBatch(
                id=allocate_id(db),
                agent_id=agent_id,
                owner_user_id=actor.user_id,
                session_id=actor.session_id,
                request_id=key,
                request_hash=fingerprint,
                suite_id=suite_id,
                suite_version=version,
                grader_version=GRADER_VERSION,
                configuration_hash=digest(snapshot),
                configuration_snapshot=deepcopy(snapshot),
                total=count,
                status="queued",
            )
            db.add(row)
            chosen = random.Random(key).sample(available, count)
            for ordinal, case in enumerate(chosen, 1):
                db.add(
                    EvaluationCase(
                        batch_id=row.id,
                        ordinal=ordinal,
                        question_id=case["id"],
                        prompt=exam_prompt(case),
                        functions=case["functions"],
                        expected=case["expected"],
                        status="pending",
                    )
                )
            db.flush()
            return summary(db, row)

    def cancel(self, actor: Actor, batch_id: str) -> dict:
        require_permission(actor, "runs:cancel")
        with self.database.transaction() as db:
            reserve_writer(db, EvaluationBatch.__table__)
            row = require_batch(db, actor, batch_id)
            if row.status in BATCH_ACTIVE:
                row.status = "cancelling"
                for case in db.scalars(
                    select(EvaluationCase).where(
                        EvaluationCase.batch_id == row.id,
                        EvaluationCase.status.in_(("pending", "running")),
                    )
                ):
                    if case.run_id:
                        run = optional_run(db, case.run_id)
                        if run and run.status in ACTIVE:
                            self.runs.cancel(db, run)
                            continue
                        if run:
                            # 先于取消提交的成果仍须保留并评分。
                            record_result(row, case, run)
                            continue
                    case.status, case.finished_at = "cancelled", utc_now()
                db.flush()
                finish_batch(db, row)
            return summary(db, row)
