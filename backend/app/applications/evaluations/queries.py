from collections import Counter

from sqlalchemy import func, select, true

from app.applications.evaluations.benchmark import (
    SCOPE,
)
from app.applications.evaluations.models import CASE_TERMINAL, EvaluationBatch, EvaluationCase
from app.auth.actor import Actor
from app.auth.permissions import can_read_all_resources, require_permission
from app.common.errors import (
    NotFoundError,
)
from app.runtime.execution.models import Run


def require_batch(db, actor: Actor, batch_id: str) -> EvaluationBatch:
    require_permission(actor, "runs:read")
    row = db.get(EvaluationBatch, batch_id)
    if row is None or (not can_read_all_resources(actor) and row.owner_user_id != actor.user_id):
        raise NotFoundError("evaluation_not_found", "考核记录不存在。")
    return row


def summary(db, row: EvaluationBatch) -> dict:
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


class EvaluationQueries:
    def __init__(self, database):
        self.database = database

    def trace_run(self, actor: Actor, batch_id: str, case_id: str) -> str:
        with self.database.transaction() as db:
            require_batch(db, actor, batch_id)
            case = db.get(EvaluationCase, case_id)
            if not case or case.batch_id != batch_id or not case.run_id:
                raise NotFoundError("evaluation_case_not_found", "考题执行记录不存在。")
            return case.run_id

    def list(self, actor: Actor, agent_id: str, offset: int, limit: int) -> dict:
        require_permission(actor, "runs:read")
        with self.database.transaction() as db:
            query = select(EvaluationBatch).where(
                EvaluationBatch.agent_id == agent_id,
                true()
                if can_read_all_resources(actor)
                else EvaluationBatch.owner_user_id == actor.user_id,
            )
            total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
            rows = db.scalars(
                query.order_by(EvaluationBatch.created_at.desc(), EvaluationBatch.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return {
                "items": [summary(db, row) for row in rows],
                "total": total,
                "offset": offset,
                "limit": limit,
            }

    def read(self, actor: Actor, batch_id: str, offset: int = 0, limit: int = 20) -> dict:
        with self.database.transaction() as db:
            row = require_batch(db, actor, batch_id)
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
                "batch": summary(db, row),
                "cases": {"items": items, "total": row.total, "offset": offset, "limit": limit},
            }
