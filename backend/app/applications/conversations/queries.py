from sqlalchemy.orm import Session

from app.applications.conversations.projections import ConversationProjection
from app.applications.conversations.schemas import (
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
from app.auth.actor import Actor
from app.common.schemas import Page
from app.infrastructure.database.session import Database
from app.resources.knowledge.schemas import KnowledgeEvidenceRead, KnowledgeEvidenceReference
from app.runtime.execution.knowledge_evidence import KnowledgeEvidence
from app.runtime.execution.queries import ExecutionQueries


class ConversationQueries:
    def __init__(
        self,
        database: Database,
        *,
        executions: ExecutionQueries | None = None,
        knowledge: KnowledgeEvidence | None = None,
    ) -> None:
        self.database = database
        self.executions, self.knowledge = executions, knowledge

    def trace(
        self,
        actor: Actor,
        conversation_id: str,
        response_id: str | None = None,
        *,
        offset: int = 0,
        limit: int = 100,
        action_id: str | None = None,
    ) -> dict:
        """先确认业务归属，再读取执行诊断并补齐对话上下文。"""
        assert self.executions is not None
        run_id = self.trace_run(actor, conversation_id, response_id)
        result = self.executions.read(
            actor, run_id, offset=offset, limit=limit, action_id=action_id
        )
        result["context"] = self.trace_context(actor, conversation_id, run_id)
        return result

    def trace_evidence(
        self, actor: Actor, conversation_id: str, response_id: str, action_id: str, direction: str
    ) -> bytes:
        assert self.executions is not None
        run_id = self.trace_run(actor, conversation_id, response_id)
        return self.executions.download(actor, run_id, action_id, direction)

    def knowledge_references(self, actor: Actor, run_id: str) -> list[KnowledgeEvidenceReference]:
        assert self.knowledge is not None
        return self.knowledge.references(actor, run_id)

    def knowledge_preview(
        self, actor: Actor, run_id: str, evidence_id: str, offset: int = 0
    ) -> KnowledgeEvidenceRead:
        assert self.knowledge is not None
        return self.knowledge.preview(actor, run_id, evidence_id, offset)

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
