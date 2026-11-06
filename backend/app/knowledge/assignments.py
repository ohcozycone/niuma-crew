"""Knowledge assignments owner, independent of SDK tool registration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.employees.models import Agent
from app.errors import ConflictError, InvalidInputError, NotFoundError
from app.infrastructure.database.transactions import reserve_writer
from app.knowledge.models import (
    EmployeeKnowledgeLibrary,
    EmployeeKnowledgeSettings,
    KnowledgeBase,
)
from app.knowledge.schemas import (
    EmployeeKnowledgeInput,
    EmployeeKnowledgeRead,
)
from app.values import new_uuid, utc_now

if TYPE_CHECKING:
    from app.knowledge.service import KnowledgeService


class KnowledgeAssignments:
    def __init__(self, knowledge: KnowledgeService) -> None:
        self.knowledge = knowledge

    @staticmethod
    def require_agent(db: Session, id: str) -> Agent:
        agent = db.get(Agent, id)
        if agent is None:
            raise NotFoundError("agent_not_found", "员工不存在。")
        return agent

    def owner(self, actor: Actor) -> str:
        require_permission(actor, "runs:create")
        return self.knowledge.owner(actor)

    @staticmethod
    def settings(db: Session, agent_id: str, user_id: str) -> EmployeeKnowledgeSettings | None:
        return db.scalar(
            select(EmployeeKnowledgeSettings).where(
                EmployeeKnowledgeSettings.agent_id == agent_id,
                EmployeeKnowledgeSettings.user_id == user_id,
            )
        )

    @staticmethod
    def library_ids(db: Session, settings: EmployeeKnowledgeSettings | None) -> list[str]:
        if settings is None:
            return []
        return list(
            db.scalars(
                select(EmployeeKnowledgeLibrary.knowledge_base_id)
                .where(
                    EmployeeKnowledgeLibrary.settings_id == settings.id,
                )
                .order_by(EmployeeKnowledgeLibrary.knowledge_base_id)
            )
        )

    def read(self, db: Session, agent_id: str, user_id: str) -> EmployeeKnowledgeRead:
        setting = self.settings(db, agent_id, user_id)
        return EmployeeKnowledgeRead(
            agent_id=agent_id,
            revision=setting.revision if setting else 0,
            knowledge_base_ids=self.library_ids(db, setting),
            mode=cast(Any, setting.mode if setting else "on_demand"),
            strategy=cast(Any, setting.strategy if setting else "auto"),
            top_k=setting.top_k if setting else 6,
            libraries=[
                self.knowledge.base_read(db, base)
                for base in db.scalars(
                    select(KnowledgeBase)
                    .where(KnowledgeBase.owner_user_id == user_id)
                    .order_by(KnowledgeBase.updated_at.desc(), KnowledgeBase.id)
                )
            ],
        )

    def get(self, actor: Actor, agent_id: str) -> EmployeeKnowledgeRead:
        user_id = self.owner(actor)
        with self.knowledge.database.transaction() as db:
            self.require_agent(db, agent_id)
            return self.read(db, agent_id, user_id)

    def replace(
        self, actor: Actor, agent_id: str, data: EmployeeKnowledgeInput
    ) -> EmployeeKnowledgeRead:
        user_id = self.owner(actor)
        ids = sorted(str(id) for id in data.knowledge_base_ids)
        if len(set(ids)) != len(ids):
            raise InvalidInputError("knowledge_duplicate_library", "不能重复装配同一知识库。")
        with self.knowledge.database.transaction() as db:
            reserve_writer(db, EmployeeKnowledgeSettings.__table__)
            self.require_agent(db, agent_id)
            for id in ids:
                self.knowledge.require_base(db, id, actor)
            setting = self.settings(db, agent_id, user_id)
            if data.expected_revision != (setting.revision if setting else 0):
                raise ConflictError(
                    "configuration_revision_conflict", "知识库装配已变化，请载入最新设置。"
                )
            if setting is None:
                setting = EmployeeKnowledgeSettings(
                    id=new_uuid(), user_id=user_id, agent_id=agent_id, revision=1
                )
                db.add(setting)
                changed = True
            else:
                changed = ids != self.library_ids(db, setting) or any(
                    getattr(setting, key) != getattr(data, key)
                    for key in ("mode", "strategy", "top_k")
                )
                if changed:
                    setting.revision += 1
            if changed:
                setting.mode, setting.strategy, setting.top_k = data.mode, data.strategy, data.top_k
                setting.updated_at = utc_now()
                db.flush()
                db.execute(
                    delete(EmployeeKnowledgeLibrary).where(
                        EmployeeKnowledgeLibrary.settings_id == setting.id
                    )
                )
                db.add_all(
                    EmployeeKnowledgeLibrary(settings_id=setting.id, knowledge_base_id=id)
                    for id in ids
                )
                db.flush()
            return self.read(db, agent_id, user_id)

    def capture(self, db: Session, agent_id: str, user_id: str | None) -> dict | None:
        if user_id is None:
            return None
        setting = self.settings(db, agent_id, user_id)
        ids = self.library_ids(db, setting)
        if not setting or not ids:
            return None
        libraries = []
        for id in ids:
            base = db.get(KnowledgeBase, id)
            if base is None or base.owner_user_id != user_id:
                raise ConflictError(
                    "knowledge_access_revoked", "知识库装配范围已变化，请重新配置。"
                )
            libraries.append({"id": id, "name": base.name, "description": base.description})
        return {
            "user_id": user_id,
            "agent_id": agent_id,
            "revision": setting.revision,
            "mode": setting.mode,
            "strategy": setting.strategy,
            "top_k": setting.top_k,
            "libraries": libraries,
        }
