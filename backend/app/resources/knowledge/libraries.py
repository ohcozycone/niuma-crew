from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.common.errors import ConflictError, InvalidInputError, NotFoundError
from app.common.values import utc_now
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.resources.knowledge.access import require_library
from app.resources.knowledge.models import (
    KnowledgeBase,
    LibraryChunk,
    LibraryDocument,
)
from app.resources.knowledge.schemas import (
    LibraryCreate,
    LibraryRead,
    LibraryUpdate,
    effective_rules,
)
from app.resources.knowledge.sources import index_summary


class KnowledgeLibraries:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def manager(actor: Actor) -> str:
        require_permission(actor, "knowledge:manage")
        if actor.user_id is None:
            raise NotFoundError("knowledge_not_found", "知识库不存在。")
        return actor.user_id

    def require_base(self, session: Session, id: str, actor: Actor) -> KnowledgeBase:
        return require_library(session, id, actor)

    @staticmethod
    def base_read(session: Session, row: KnowledgeBase) -> LibraryRead:
        rules = effective_rules(row.chunk_size, row.chunk_overlap, row.min_section_chars)
        document_count = (
            session.scalar(
                select(func.count())
                .select_from(LibraryDocument)
                .where(LibraryDocument.knowledge_base_id == row.id)
            )
            or 0
        )
        chunk_count = (
            session.scalar(
                select(func.count())
                .select_from(LibraryChunk)
                .join(LibraryDocument, LibraryDocument.id == LibraryChunk.document_id)
                .where(LibraryDocument.knowledge_base_id == row.id)
            )
            or 0
        )
        return LibraryRead(
            id=row.id,
            name=row.name,
            description=row.description,
            document_count=document_count,
            chunk_count=chunk_count,
            updated_at=row.updated_at,
            revision=row.revision,
            chunk_size=row.chunk_size,
            chunk_overlap=row.chunk_overlap,
            min_section_chars=row.min_section_chars,
            effective_chunk_size=rules.chunk_size,
            effective_chunk_overlap=rules.chunk_overlap,
            effective_min_section_chars=rules.min_section_chars,
            keyword_document_count=session.scalar(
                select(func.count())
                .select_from(LibraryDocument)
                .where(
                    LibraryDocument.knowledge_base_id == row.id,
                    LibraryDocument.lexical_version != "",
                )
            )
            or 0,
            processing_document_count=session.scalar(
                select(func.count())
                .select_from(LibraryDocument)
                .where(
                    LibraryDocument.knowledge_base_id == row.id,
                    LibraryDocument.active_job_id.is_not(None),
                )
            )
            or 0,
            **index_summary(session, row.id, chunk_count),
        )

    def libraries(self, actor: Actor) -> list[LibraryRead]:
        if actor.kind == "guest":
            require_permission(actor, "knowledge:read")
        else:
            self.manager(actor)
        with self.database.transaction() as session:
            return [
                self.base_read(session, row)
                for row in session.scalars(
                    select(KnowledgeBase).order_by(
                        KnowledgeBase.updated_at.desc(), KnowledgeBase.id
                    )
                )
            ]

    def get(self, actor: Actor, id: str) -> LibraryRead:
        with self.database.transaction() as session:
            return self.base_read(session, self.require_base(session, id, actor))

    def create(self, actor: Actor, data: LibraryCreate) -> LibraryRead:
        owner = self.manager(actor)
        with self.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            old = session.scalar(
                select(KnowledgeBase).where(
                    KnowledgeBase.created_by_user_id == owner,
                    KnowledgeBase.client_request_id == str(data.client_request_id),
                )
            )
            if old:
                if old.name != data.name or old.description != data.description:
                    raise ConflictError(
                        "knowledge_request_conflict", "该提交标识已用于其他知识库内容。"
                    )
                return self.base_read(session, old)
            if (
                session.scalar(
                    select(func.count())
                    .select_from(KnowledgeBase)
                    .where(KnowledgeBase.created_by_user_id == owner)
                )
                or 0
            ) >= 100:
                raise InvalidInputError(
                    "knowledge_quota_exceeded", "每个账号最多创建 100 个知识库。"
                )
            row = KnowledgeBase(
                created_by_user_id=owner,
                client_request_id=str(data.client_request_id),
                name=data.name,
                description=data.description,
            )
            session.add(row)
            session.flush()
            return self.base_read(session, row)

    def update(self, actor: Actor, id: str, data: LibraryUpdate) -> LibraryRead:
        """仅更新元数据及规则，不重建已入库文件。"""
        self.manager(actor)
        try:
            effective_rules(data.chunk_size, data.chunk_overlap, data.min_section_chars)
        except ValueError:
            raise InvalidInputError(
                "knowledge_chunk_rule_invalid",
                "重叠必须小于切分长度，短章节阈值不能超过两者之差；请检查合并后的规则。",
            ) from None
        with self.database.transaction() as session:
            reserve_writer(session, KnowledgeBase.__table__)
            row = self.require_base(session, id, actor)
            if row.revision != data.expected_revision:
                raise ConflictError(
                    "configuration_revision_conflict", "知识库设置已变化，请刷新后再修改。"
                )
            values = data.model_dump(exclude={"expected_revision"})
            if any(getattr(row, key) != value for key, value in values.items()):
                for key, value in values.items():
                    setattr(row, key, value)
                row.revision += 1
                row.updated_at = utc_now()
                session.flush()
            return self.base_read(session, row)

    def read_in(self, db: Session, id: str) -> LibraryRead:
        row = db.get(KnowledgeBase, id)
        if row is None:
            raise NotFoundError("knowledge_not_found", "知识库不存在。")
        return self.base_read(db, row)


def library_fact(db: Session, id: str) -> dict[str, str] | None:
    row = db.get(KnowledgeBase, id)
    return dict(id=row.id, name=row.name, description=row.description) if row else None
