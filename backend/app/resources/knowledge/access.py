from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.common.errors import NotFoundError
from app.resources.knowledge.models import KnowledgeBase


def require_library(db: Session, id: str, actor: Actor) -> KnowledgeBase:
    require_permission(actor, "knowledge:read" if actor.kind == "guest" else "knowledge:manage")
    row = db.get(KnowledgeBase, id)
    if row is None:
        raise NotFoundError("knowledge_not_found", "知识库不存在。")
    return row
