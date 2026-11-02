"""Product file visibility and retention compose resource references here."""

from sqlalchemy import select

from app.auth.permissions import require_permission
from app.conversations.models import ConversationRun, Message, MessageFile
from app.conversations.queries import require_conversation
from app.errors import NotFoundError
from app.execution.models import ACTIVE, Run, RunAction
from app.files.models import StoredFile
from app.files.service import file_ref


def retained_file_ids(db, candidates):
    ids = {row.id for row in candidates}
    origins = {row.origin_run_id for row in candidates if row.origin_run_id}
    retained = set(db.scalars(select(MessageFile.file_id).where(MessageFile.file_id.in_(ids))))
    active = set(db.scalars(select(Run.id).where(Run.id.in_(origins), Run.status.in_(ACTIVE))))
    retained.update(row.id for row in candidates if row.origin_run_id in active)
    for details in db.scalars(
        select(RunAction.safe_details).where(
            RunAction.run_id.in_(origins), RunAction.kind == "tool_call"
        )
    ):
        retained.add(details.get("result_file_id"))
        retained.update(source.get("file_id") for source in details.get("sources", []))
    return retained


class ConversationFiles:
    def __init__(self, database, files):
        self.database, self.files = database, files

    def list(self, actor, conversation_id):
        require_permission(actor, "conversations:read")
        with self.database.transaction() as db:
            require_conversation(db, conversation_id, actor)
            rows = db.scalars(
                select(StoredFile)
                .join(MessageFile, MessageFile.file_id == StoredFile.id)
                .join(Message, Message.id == MessageFile.message_id)
                .where(Message.conversation_id == conversation_id)
                .distinct()
            )
            return [file_ref(row) for row in rows]

    def download(self, actor, conversation_id, file_id):
        require_permission(actor, "conversations:read")
        with self.database.transaction() as db:
            require_conversation(db, conversation_id, actor)
            row = db.get(StoredFile, file_id)
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
