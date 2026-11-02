"""Publish stable outputs and product state in the same business transaction."""

import logging
from collections.abc import Callable
from dataclasses import replace

from sqlalchemy.orm import Session

from app.conversations.writes import publish_conversation
from app.execution.contracts import Completion
from app.execution.errors import PublicationFailure, terminal_status
from app.execution.models import ACTIVE, Run
from app.execution.queries import require_run
from app.execution.store import RunStore
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer

logger = logging.getLogger(__name__)

ResultPublisher = Callable[[Session, Run, str | None], None]


class PublishRun:
    def __init__(
        self,
        database: Database,
        authorize: Callable[..., None],
        publish_content: ResultPublisher = publish_conversation,
        prepare_content: Callable[[Session, Run, str], str] | None = None,
    ) -> None:
        self.database, self.authorize = database, authorize
        self.publish_content = publish_content
        self.prepare_content = prepare_content

    def finish(self, db: Session, row: Run, intent: Completion) -> None:
        if row.status not in ACTIVE:
            return
        if row.status == "cancelling":
            intent = replace(intent, status="cancelled", content=None, error=None, structured=None)
        if intent.status != "succeeded" and not row.config_snapshot.get(
            "allow_partial_output", True
        ):
            intent = replace(intent, content=None, structured=None)
        if intent.status == "succeeded":
            try:
                self.authorize(row, db=db)
                if self.prepare_content is not None and intent.content:
                    intent = replace(intent, content=self.prepare_content(db, row, intent.content))
            except Exception as error:
                if not hasattr(error, "code"):
                    raise
                code = error.code
                intent = replace(
                    intent, status=terminal_status(code), error=code, content=None, structured=None
                )
        if intent.status == "succeeded" and not (intent.content and intent.content.strip()):
            raise ValueError("Successful execution requires a nonempty answer")
        RunStore.finish(db, row, intent)
        if intent.status == "succeeded" and intent.structured:
            from app.conversations.models import ConversationRun, MessageFile
            from app.files.models import StoredFile

            binding = db.get(ConversationRun, row.id)
            for ref in intent.structured.get("output_files", []):
                file = db.get(StoredFile, ref["id"])
                if (
                    file is None
                    or file.origin_run_id != row.id
                    or file.owner_user_id != row.owner_user_id
                    or file.purpose != "output"
                    or file.content_hash != ref["content_hash"]
                ):
                    raise ValueError("Output file does not belong to this execution")
                if binding is None:
                    raise ValueError("Missing conversation binding")
                db.add(MessageFile(message_id=binding.reply_message_id, file_id=file.id))
        self.publish_content(db, row, intent.content)
        db.flush()

    def __call__(self, intent: Completion) -> None:
        try:
            with self.database.transaction() as db:
                reserve_writer(db, Run.__table__)
                row = require_run(db, intent.run_id)
                changed = row.status in ACTIVE
                self.finish(db, row, intent)
                status = row.status
            if changed:
                logger.info("execution.published run=%s status=%s", intent.run_id, status)
        except PublicationFailure:
            raise
        except Exception as error:
            raise PublicationFailure("结果事务未能提交。") from error
