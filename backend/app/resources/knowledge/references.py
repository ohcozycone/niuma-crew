from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import ConflictError
from app.resources.files.contracts import FileRetentionCandidate
from app.resources.knowledge.models import LibraryDocument, LibraryVectorIndex, VectorJob


def assert_model_unused(db: Session, connection_id: str) -> None:
    if db.scalar(
        select(LibraryVectorIndex.knowledge_base_id)
        .where(LibraryVectorIndex.connection_id == connection_id)
        .limit(1)
    ) or db.scalar(
        select(VectorJob.id)
        .where(
            VectorJob.connection_id == connection_id, VectorJob.status.in_(("queued", "running"))
        )
        .limit(1)
    ):
        raise ConflictError(
            "model_connection_in_use", "仍有知识库使用此向量连接，请先移除对应向量索引。"
        )


def retained_file_ids(session: Session, candidates: list[FileRetentionCandidate]) -> set[str]:
    return set(
        session.scalars(
            select(LibraryDocument.file_id).where(
                LibraryDocument.file_id.in_([row.id for row in candidates])
            )
        )
    )
