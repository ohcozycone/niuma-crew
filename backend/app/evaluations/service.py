"""Durable, owner-scoped exams using the same independent Run admission."""

import logging
import random
from collections import Counter
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
    ServiceError,
    ServiceUnavailableError,
)
from app.evaluations.benchmark import (
    GRADER_VERSION,
    SCOPE,
    SUITE_ID,
    exam_prompt,
    grade,
    load_suite,
)
from app.evaluations.models import BATCH_ACTIVE, CASE_TERMINAL, EvaluationBatch, EvaluationCase
from app.execution.models import ACTIVE, Run
from app.execution.service import RunService
from app.infrastructure.database.identifiers import allocate_id
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.values import digest, utc_now

logger = logging.getLogger(__name__)


class EvaluationService:
    def __init__(self, database: Database, runs: RunService) -> None:
        self.database, self.runs = database, runs

    @staticmethod
    def _require(db, actor: Actor, batch_id: str) -> EvaluationBatch:
        require_permission(actor, "runs:read")
        row = db.get(EvaluationBatch, batch_id)
        if row is None or row.owner_user_id != actor.user_id:
            raise NotFoundError("evaluation_not_found", "考核记录不存在。")
        return row

    def trace_run(self, actor: Actor, batch_id: str, case_id: str) -> str:
        with self.database.transaction() as db:
            self._require(db, actor, batch_id)
            case = db.get(EvaluationCase, case_id)
            if not case or case.batch_id != batch_id or not case.run_id:
                raise NotFoundError("evaluation_case_not_found", "考题执行记录不存在。")
            return case.run_id

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
                return self._summary(db, existing)
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
                db, agent_id, "考核配置核对", [], actor.user_id, tools_enabled=False
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
            return self._summary(db, row)

    def list(self, actor: Actor, agent_id: str, offset: int, limit: int) -> dict:
        require_permission(actor, "runs:read")
        with self.database.transaction() as db:
            query = select(EvaluationBatch).where(
                EvaluationBatch.agent_id == agent_id,
                EvaluationBatch.owner_user_id == actor.user_id,
            )
            total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
            rows = db.scalars(
                query.order_by(EvaluationBatch.created_at.desc(), EvaluationBatch.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return {
                "items": [self._summary(db, row) for row in rows],
                "total": total,
                "offset": offset,
                "limit": limit,
            }

    def read(self, actor: Actor, batch_id: str, offset: int = 0, limit: int = 20) -> dict:
        with self.database.transaction() as db:
            row = self._require(db, actor, batch_id)
            cases = db.scalars(
                select(EvaluationCase)
                .where(EvaluationCase.batch_id == row.id)
                .order_by(EvaluationCase.ordinal)
                .offset(offset)
                .limit(limit)
            )
            items = []
            for case in cases:
                run = db.get(Run, case.run_id) if case.run_id else None
                graded = case.status in ("passed", "failed")
                items.append(
                    {
                        "id": case.id,
                        "ordinal": case.ordinal,
                        "question_id": case.question_id,
                        "status": case.status,
                        "run_id": case.run_id,
                        "run_status": run.status if run else None,
                        "question": case.prompt,
                        "functions": case.functions,
                        "answer": case.answer,
                        "grading": case.grading,
                        "expected": case.expected if graded else None,
                        "error_code": case.error_code,
                        "usage": run.usage if run else None,
                    }
                )
            return {
                "batch": self._summary(db, row),
                "cases": {"items": items, "total": row.total, "offset": offset, "limit": limit},
            }

    @staticmethod
    def _summary(db, row: EvaluationBatch) -> dict:
        counts = Counter(
            dict(
                db.execute(
                    select(EvaluationCase.status, func.count())
                    .where(EvaluationCase.batch_id == row.id)
                    .group_by(EvaluationCase.status)
                ).all()
            )
        )
        snapshot = row.configuration_snapshot
        scored = counts["passed"] + counts["failed"]
        return {
            "id": row.id,
            "agent_id": row.agent_id,
            "suite_id": row.suite_id,
            "name": "工具调用专项 · BFCL",
            "suite_version": row.suite_version,
            "grader_version": row.grader_version,
            "scope": SCOPE,
            "status": row.status,
            "total": row.total,
            "completed": sum(counts[s] for s in CASE_TERMINAL),
            "scored": scored,
            "passed": counts["passed"],
            "failed": counts["failed"],
            "errors": counts["error"],
            "cancelled": counts["cancelled"],
            "pass_rate": counts["passed"] / scored if scored else None,
            "configuration_hash": row.configuration_hash,
            "agent_revision": snapshot["agent_revision"],
            "model_id": snapshot["model_id"],
            "created_at": row.created_at,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "error_code": row.error_code,
        }

    def cancel(self, actor: Actor, batch_id: str) -> dict:
        require_permission(actor, "runs:cancel")
        with self.database.transaction() as db:
            reserve_writer(db, EvaluationBatch.__table__)
            row = self._require(db, actor, batch_id)
            if row.status in BATCH_ACTIVE:
                row.status = "cancelling"
                for case in db.scalars(
                    select(EvaluationCase).where(
                        EvaluationCase.batch_id == row.id,
                        EvaluationCase.status.in_(("pending", "running")),
                    )
                ):
                    if case.run_id:
                        run = db.get(Run, case.run_id)
                        if run and run.status in ACTIVE:
                            self.runs.cancel(db, run)
                            continue
                        if run:
                            # Completion committed before this cancellation owns
                            # the result; retain and score it instead of hiding it.
                            self._record_result(row, case, run)
                            continue
                    case.status, case.finished_at = "cancelled", utc_now()
                db.flush()
                self._finish(db, row)
            return self._summary(db, row)

    @staticmethod
    def _record_result(batch: EvaluationBatch, case: EvaluationCase, run: Run) -> None:
        case.answer, case.finished_at = run.result_text, utc_now()
        if run.status != "succeeded":
            case.status, case.error_code = "error", run.error_code or run.status
            return
        try:
            if batch.grader_version != GRADER_VERSION:
                raise RuntimeError("评分器版本已改变，不能重新解释旧考核。")
            case.grading = grade(case.functions, case.expected, case.answer or "")
            case.status = "passed" if case.grading["valid"] else "failed"
        except Exception as error:
            case.status, case.error_code = "error", "grading_failed"
            logger.warning(
                "evaluation.grade_failed batch=%s type=%s", batch.id, type(error).__name__
            )

    @staticmethod
    def _finish(db, row: EvaluationBatch) -> None:
        unfinished = db.scalar(
            select(func.count())
            .select_from(EvaluationCase)
            .where(
                EvaluationCase.batch_id == row.id, EvaluationCase.status.in_(("pending", "running"))
            )
        )
        if not unfinished:
            row.status = (
                "cancelled"
                if row.status == "cancelling"
                else ("failed" if row.error_code else "completed")
            )
            row.finished_at = utc_now()

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
                # Each advance owns a transaction. A rolled-back batch must not
                # prevent unrelated owners' exams from making progress.
                logger.warning(
                    "evaluation.advance_failed batch=%s type=%s", batch_id, type(error).__name__
                )

    def advance(self, batch_id: str) -> None:
        """One durable step; admission and the case binding commit atomically."""
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
                self._finish(db, batch)
                return
            if case.run_id:
                run = db.get(Run, case.run_id)
                if run.status in ACTIVE:
                    return
                if batch.status == "cancelling":
                    case.answer, case.finished_at, case.status = (
                        run.result_text,
                        utc_now(),
                        "cancelled",
                    )
                else:
                    self._record_result(batch, case, run)
                db.flush()
                self._finish(db, batch)
                return
            if batch.status == "cancelling":
                case.status, case.finished_at = "cancelled", utc_now()
                db.flush()
                self._finish(db, batch)
                return
            try:
                actor = authorize_work(db, batch.owner_user_id, batch.session_id)
                snapshot, _ = self.runs.configuration.prepare(
                    db, batch.agent_id, case.prompt, [], actor.user_id, tools_enabled=False
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
                    thread_id="evaluation:" + case.id,
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
                self._finish(db, batch)
                return
            case.run_id, case.status = run.id, "running"
            batch.status, batch.started_at = "running", batch.started_at or utc_now()
