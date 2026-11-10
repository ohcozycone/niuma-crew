from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ConflictError
from app.knowledge.models import LibraryVectorIndex


def assert_model_unused(db: Session, connection_id: str) -> None:
    if db.scalar(
        select(LibraryVectorIndex.knowledge_base_id)
        .where(LibraryVectorIndex.connection_id == connection_id)
        .limit(1)
    ):
        raise ConflictError(
            "model_connection_in_use", "仍有知识库使用此向量连接，请先移除对应向量索引。"
        )
