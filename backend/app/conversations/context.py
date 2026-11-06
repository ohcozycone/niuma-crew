"""Select the execution whose result was accepted by the conversation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conversations.models import ConversationRun, Message
from app.execution.models import Run


def accepted_run_id(db: Session, conversation_id: str) -> str | None:
    """Return the accepted branch, without reading message text or SDK storage."""
    return db.scalar(
        select(Run.id)
        .join(ConversationRun, ConversationRun.run_id == Run.id)
        .join(Message, Message.id == ConversationRun.run_id)
        .where(
            ConversationRun.conversation_id == conversation_id,
            Run.status == "succeeded",
            ConversationRun.handled_at.is_not(None),
            ConversationRun.acceptance_error.is_(None),
        )
        .order_by(Message.sequence.desc())
        .limit(1)
    )
