import logging

from sqlalchemy import func, select

from app.applications.evaluations.benchmark import (
    GRADER_VERSION,
    grade,
)
from app.applications.evaluations.models import EvaluationBatch, EvaluationCase
from app.common.values import utc_now
from app.runtime.contracts.runs import RunState

logger = logging.getLogger(__name__)


def record_result(batch: EvaluationBatch, case: EvaluationCase, run: RunState) -> None:
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
        logger.warning("evaluation.grade_failed batch=%s type=%s", batch.id, type(error).__name__)


def finish_batch(db, row: EvaluationBatch) -> None:
    unfinished = db.scalar(
        select(func.count())
        .select_from(EvaluationCase)
        .where(EvaluationCase.batch_id == row.id, EvaluationCase.status.in_(("pending", "running")))
    )
    if not unfinished:
        row.status = (
            "cancelled"
            if row.status == "cancelling"
            else ("failed" if row.error_code else "completed")
        )
        row.finished_at = utc_now()
