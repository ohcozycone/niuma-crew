from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.employees.models import Agent, AgentKnowledgeLibrary
from app.errors import InvalidInputError, NotFoundError
from app.knowledge.models import KnowledgeBase


def knowledge_ids(db: Session, agent_id: str) -> list[str]:
    return list(
        db.scalars(
            select(AgentKnowledgeLibrary.knowledge_base_id)
            .where(AgentKnowledgeLibrary.agent_id == agent_id)
            .order_by(AgentKnowledgeLibrary.knowledge_base_id)
        )
    )


def knowledge_configuration(db: Session, agent: Agent) -> dict[str, Any]:
    return {
        "knowledge_base_ids": knowledge_ids(db, agent.id),
        "mode": agent.knowledge_mode,
        "top_k": agent.knowledge_top_k,
    }


def replace_knowledge(db: Session, agent: Agent, data: Any) -> None:
    ids = sorted(str(value) for value in data.knowledge_base_ids)
    if len(set(ids)) != len(ids):
        raise InvalidInputError("knowledge_duplicate_library", "不能重复装配同一知识库。")
    for identifier in ids:
        if db.get(KnowledgeBase, identifier) is None:
            raise NotFoundError("knowledge_not_found", "待装配知识库不存在。")
    agent.knowledge_mode, agent.knowledge_top_k = data.mode, data.top_k
    db.execute(delete(AgentKnowledgeLibrary).where(AgentKnowledgeLibrary.agent_id == agent.id))
    db.add_all(AgentKnowledgeLibrary(agent_id=agent.id, knowledge_base_id=value) for value in ids)


def capture_knowledge(db: Session, agent_id: str) -> dict[str, Any] | None:
    """在受理事务中捕获员工固定范围；发起用户不参与选库。"""
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise NotFoundError("agent_not_found", "员工不存在。")
    ids = knowledge_ids(db, agent_id)
    if not ids:
        return None
    libraries = []
    for identifier in ids:
        base = db.get(KnowledgeBase, identifier)
        if base is None:
            raise NotFoundError("knowledge_not_found", "员工装配的知识库不存在。")
        libraries.append({"id": base.id, "name": base.name, "description": base.description})
    return {
        "agent_id": agent.id,
        "revision": agent.revision,
        "mode": agent.knowledge_mode,
        "top_k": agent.knowledge_top_k,
        "libraries": libraries,
    }
