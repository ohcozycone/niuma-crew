from sqlalchemy import select

from app.errors import ConflictError
from app.execution.models import ACTIVE, Run


def assert_model_unused(db, connection_id):
    if db.scalar(
        select(Run.id)
        .where(Run.model_connection_id == connection_id, Run.status.in_(ACTIVE))
        .limit(1)
    ):
        raise ConflictError("model_connection_in_use", "仍有执行使用这个大脑，请等待结束或停止。")
