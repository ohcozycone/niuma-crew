"""Conversation access ownership."""

from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_resource_access
from app.conversations.models import Conversation, ConversationRun
from app.errors import NotFoundError
from app.execution.models import Run


def require_conversation(db: Session, id: str, actor: Actor) -> Conversation:
    row = db.get(Conversation, id)
    if not row:
        raise NotFoundError("conversation_not_found", "对话不存在。")
    require_resource_access(actor, row.owner_user_id)
    return row


def require_binding(db: Session, row: Run) -> ConversationRun:
    binding = db.get(ConversationRun, row.id)
    if row.origin_kind != "conversation" or binding is None:
        raise NotFoundError("conversation_run_not_found", "对话执行记录不存在。")
    return binding


def require_response(db: Session, actor: Actor, conversation_id: str, response_id: str) -> Run:
    require_conversation(db, conversation_id, actor)
    binding = db.scalar(
        select(ConversationRun).where(
            ConversationRun.conversation_id == conversation_id,
            ConversationRun.run_id == response_id,
        )
    )
    if not binding:
        raise NotFoundError("response_not_found", "回复不存在。")
    return cast(Run, db.get(Run, binding.run_id))
