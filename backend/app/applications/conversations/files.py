from sqlalchemy import select

from app.applications.conversations.access import require_conversation
from app.applications.conversations.models import ConversationRun, Message, MessageFile
from app.auth.permissions import require_permission
from app.common.errors import NotFoundError
from app.resources.files.service import file_ref


def retained_file_ids(db, candidates):
    ids = {row.id for row in candidates}
    retained = set(db.scalars(select(MessageFile.file_id).where(MessageFile.file_id.in_(ids))))
    return retained


class ConversationFiles:
    def __init__(self, database, files):
        self.database, self.files = database, files

    def list(self, actor, conversation_id):
        require_permission(actor, "conversations:read")
        with self.database.transaction() as db:
            require_conversation(db, conversation_id, actor)
            ids = db.scalars(
                select(MessageFile.file_id)
                .join(Message, Message.id == MessageFile.message_id)
                .where(Message.conversation_id == conversation_id)
                .distinct()
            )
            return [file_ref(info) for id in ids if (info := self.files.metadata(db, id))]

    def download(self, actor, conversation_id, file_id):
        require_permission(actor, "conversations:read")
        with self.database.transaction() as db:
            require_conversation(db, conversation_id, actor)
            row = self.files.metadata(db, file_id)
            associated = db.scalar(
                select(MessageFile.file_id)
                .join(Message, Message.id == MessageFile.message_id)
                .where(Message.conversation_id == conversation_id, MessageFile.file_id == file_id)
                .limit(1)
            )
            source = (
                row is not None
                and row.purpose == "source"
                and db.scalar(
                    select(ConversationRun.run_id).where(
                        ConversationRun.conversation_id == conversation_id,
                        ConversationRun.run_id == row.origin_run_id,
                    )
                )
            )
            if row is None or (not associated and not source):
                raise NotFoundError("file_not_found", "文件不存在或尚未发布。")
            ref = file_ref(row)
        return ref, self.files.read(file_id)
