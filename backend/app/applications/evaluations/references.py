from sqlalchemy import select

from app.applications.evaluations.models import EvaluationBatch
from app.common.errors import ConflictError


def assert_employee_unused(db, agent_id):
    if db.scalar(select(EvaluationBatch.id).where(EvaluationBatch.agent_id == agent_id).limit(1)):
        raise ConflictError("agent_has_evaluations", "员工已有考核记录，请改为停用。")
