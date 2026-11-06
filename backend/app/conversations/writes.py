"""Conversation mutations participate in the caller's transaction without committing."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conversations.access import require_binding
from app.conversations.models import Conversation, ConversationRun, Message
from app.errors import ConflictError
from app.execution.models import Run
from app.infrastructure.database.identifiers import allocate_id
from app.values import utc_now


def create_conversation(
    db: Session, agent_id: str, owner_user_id: str | None, conversation_id: str | None = None
) -> Conversation:
    row = Conversation(id=allocate_id(db), agent_id=agent_id, owner_user_id=owner_user_id)
    if conversation_id is not None:
        row.id = conversation_id
    db.add(row)
    db.flush()
    return row


def require_idle(db: Session, conversation: Conversation) -> None:
    if db.scalar(
        select(ConversationRun.run_id).where(
            ConversationRun.conversation_id == conversation.id, ConversationRun.active.is_(True)
        )
    ):
        raise ConflictError("conversation_busy", "此对话仍在执行，请等待或停止后再发送。")


def prepare_input(
    db: Session, conversation: Conversation, content: str, previous: ConversationRun | None
) -> Message:
    if previous:
        message = db.get(Message, previous.input_message_id)
        if message is None:
            raise ValueError("重试输入不存在。")
        return message
    conversation.last_message_sequence += 1
    message = Message(
        id=allocate_id(db),
        conversation_id=conversation.id,
        sequence=conversation.last_message_sequence,
        role="user",
        body=content,
    )
    db.add(message)
    db.flush()
    if conversation.last_message_sequence == 1:
        conversation.title = content[:100]
    return message


def bind_run(
    db: Session, conversation: Conversation, message: Message, run: Run
) -> ConversationRun:
    if (
        run.origin_kind != "conversation"
        or run.owner_user_id != conversation.owner_user_id
        or run.agent_id != conversation.agent_id
        or message.conversation_id != conversation.id
    ):
        raise ValueError("执行与对话的归属不一致。")
    conversation.last_message_sequence += 1
    conversation.updated_at = utc_now()
    reply = Message(
        id=run.id,
        conversation_id=conversation.id,
        sequence=conversation.last_message_sequence,
        role="assistant",
        body=None,
    )
    db.add(reply)
    db.flush()
    conversation.revision += 1
    binding = ConversationRun(
        run_id=run.id,
        conversation_id=conversation.id,
        input_message_id=message.id,
        active=True,
    )
    db.add(binding)
    db.flush()
    return binding


def publish_conversation(db: Session, row: Run, content: str | None) -> None:
    binding = require_binding(db, row)
    conversation = db.get(Conversation, binding.conversation_id)
    if (
        conversation is None
        or conversation.agent_id != row.agent_id
        or conversation.owner_user_id != row.owner_user_id
    ):
        raise ValueError("执行与结果发布主体不一致。")
    binding.active = False
    conversation.updated_at = utc_now()
    conversation.revision += 1
    message = db.get(Message, binding.run_id)
    if message is None or message.role != "assistant":
        raise ValueError("回复记录缺失或角色错误。")
    message.body = content or None
