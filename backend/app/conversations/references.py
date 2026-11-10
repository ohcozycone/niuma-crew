from sqlalchemy import select

from app.conversations.models import Conversation
from app.errors import ConflictError


def assert_employee_unused(db, agent_id):
    if db.scalar(select(Conversation.id).where(Conversation.agent_id == agent_id).limit(1)):
        raise ConflictError("agent_has_conversations", "员工已有对话历史，请改为停用。")
