from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.conversations.projections import ConversationProjection
from app.conversations.schemas import (
    AcceptedSubmission,
    ConversationRead,
    ConversationSnapshot,
    ConversationStats,
    ConversationStatusFilter,
    MessagePage,
    QuestionPage,
    QuestionPreviewRead,
    ResponseSnapshot,
)
from app.infrastructure.database.session import Database
from app.schemas import Page


class ConversationQueries:
    def __init__(self, database: Database) -> None:
        self.database = database

    def trace_context(self, actor: Actor, conversation_id: str, response_id: str) -> dict:
        with self.database.transaction() as db:
            return ConversationProjection(db).trace_context(actor, conversation_id, response_id)

    def trace_run(self, actor: Actor, conversation_id: str, response_id: str | None = None) -> str:
        with self.database.transaction() as db:
            return ConversationProjection(db).trace_run(actor, conversation_id, response_id)

    def list(
        self,
        actor: Actor,
        agent_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
        *,
        q: str = "",
        status: ConversationStatusFilter | None = None,
    ) -> Page[ConversationRead]:
        with self.database.transaction() as db:
            return ConversationProjection(db).list(
                actor, agent_id, offset, limit, q=q, status=status
            )

    def stats(self, actor: Actor, agent_id: str) -> ConversationStats:
        with self.database.transaction() as db:
            return ConversationProjection(db).stats(actor, agent_id)

    def questions(
        self,
        actor: Actor,
        id: str,
        after: int | None = None,
        limit: int = 100,
        q: str = "",
        anchor: str | None = None,
        start_number: int | None = None,
    ) -> QuestionPage:
        with self.database.transaction() as db:
            return ConversationProjection(db).questions(
                actor, id, after, limit, q, anchor, start_number
            )

    def question_preview(self, actor: Actor, id: str, question_id: str) -> QuestionPreviewRead:
        with self.database.transaction() as db:
            return ConversationProjection(db).question_preview(actor, id, question_id)

    def messages(
        self,
        actor: Actor,
        id: str,
        before: int | None = None,
        limit: int = 50,
        after: int | None = None,
        around: str | None = None,
        db: Session | None = None,
    ) -> MessagePage:
        if db is not None:
            return ConversationProjection(db).messages(actor, id, before, limit, after, around, db)
        with self.database.transaction() as db:
            return ConversationProjection(db).messages(actor, id, before, limit, after, around, db)

    def response(self, actor: Actor, conversation_id: str, response_id: str) -> ResponseSnapshot:
        with self.database.transaction() as db:
            return ConversationProjection(db).response(actor, conversation_id, response_id)

    def snapshot(self, actor: Actor, id: str, limit: int = 50) -> ConversationSnapshot:
        with self.database.transaction() as db:
            return ConversationProjection(db).snapshot(actor, id, limit)

    def find_request(
        self, actor: Actor, conversation_id: str | None, request_id: str
    ) -> AcceptedSubmission | None:
        with self.database.transaction() as db:
            return ConversationProjection(db).find_request(actor, conversation_id, request_id)
