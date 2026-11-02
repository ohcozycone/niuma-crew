"""Conversation lookups, history, context selection and chat read projections."""

import re
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.agent_runtime.contracts import InputMessage
from app.agents.models import Agent
from app.auth.actor import Actor
from app.auth.permissions import permissions_for, require_permission, require_resource_access
from app.conversations.models import Conversation, ConversationRun, Message, MessageFile
from app.conversations.schemas import (
    AcceptedSubmission,
    AssistantMessageView,
    ContextRead,
    ConversationRead,
    ConversationSnapshot,
    MessagePage,
    PublicError,
    PublicStep,
    QuestionPage,
    QuestionPreviewRead,
    QuestionRead,
    ResponseSnapshot,
    UserMessageView,
)
from app.errors import InvalidInputError, NotFoundError
from app.execution.errors import ERROR_MESSAGES
from app.execution.models import ACTIVE, Run, RunAction
from app.files.models import StoredFile
from app.files.service import file_ref
from app.infrastructure.database.session import Database
from app.llm.usage import TokenUsage
from app.schemas import Page


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


def message_files(db: Session, id: str) -> list[dict]:
    return [
        file_ref(file)
        for file in db.scalars(
            select(StoredFile)
            .join(MessageFile, MessageFile.file_id == StoredFile.id)
            .where(MessageFile.message_id == id)
        )
    ]


def read_user(row: Message, db: Session | None = None) -> UserMessageView:
    if row.role != "user" or row.body is None:
        raise ValueError("输入消息不可读取。")
    return UserMessageView(
        id=row.id,
        conversation_id=row.conversation_id,
        sequence=row.sequence,
        content=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
        files=message_files(db, row.id) if db is not None else [],
    )


def read_response(
    db: Session, row: Run, *, actions: list[RunAction] | None = None
) -> AssistantMessageView:
    binding = require_binding(db, row)
    reply = db.get(Message, binding.reply_message_id)
    if reply is None:
        raise ValueError("回复记录不存在。")
    if actions is None:
        actions = list(
            db.scalars(
                select(RunAction).where(RunAction.run_id == row.id).order_by(RunAction.sequence)
            )
        )
    content = reply.body or ""
    if row.status in ACTIVE:
        latest_model = next((item for item in reversed(actions) if item.kind == "model_call"), None)
        content = (
            latest_model.output_text
            if latest_model and not latest_model.safe_details.get("has_tool_calls")
            else ""
        )
    retired = bool(
        row.config_snapshot.get("retired_work")
        or row.config_snapshot.get("work")
        or row.config_snapshot.get("ci")
    )
    can_retry = False
    if not retired and row.status in {"failed", "cancelled", "interrupted"}:
        latest = db.scalar(
            select(ConversationRun.run_id)
            .join(Message, Message.id == ConversationRun.reply_message_id)
            .where(ConversationRun.conversation_id == binding.conversation_id)
            .order_by(Message.sequence.desc())
            .limit(1)
        )
        active_run = db.scalar(
            select(ConversationRun.run_id).where(
                ConversationRun.conversation_id == binding.conversation_id, ConversationRun.active
            )
        )
        can_retry = latest == row.id and active_run is None
    return AssistantMessageView(
        files=message_files(db, reply.id),
        id=reply.id,
        conversation_id=reply.conversation_id,
        sequence=reply.sequence,
        reply_to_message_id=binding.input_message_id,
        retry_of_response_id=cast(
            ConversationRun, db.get(ConversationRun, row.retry_of_run_id)
        ).reply_message_id
        if row.retry_of_run_id
        else None,
        version=row.revision,
        status=row.status,
        content=content,
        content_state="empty"
        if not content
        else "draft"
        if row.status in ACTIVE
        else "complete"
        if row.status == "succeeded"
        else "partial",
        steps=[PublicStep.model_validate(step) for step in actions],
        usage=TokenUsage.model_validate(row.usage) if row.usage is not None else None,
        error=PublicError(
            code=row.error_code,
            message=(
                "此历史功能已移除，仅可查看原记录。"
                if retired
                else ERROR_MESSAGES.get(row.error_code, "执行失败，请重试。")
            )
            + ("已保留未完成的输出。" if content and row.status == "failed" else ""),
        )
        if row.error_code
        else None,
        context=ContextRead(
            pair_count=row.config_snapshot.get("context_pair_count", 0),
            truncated=row.config_snapshot.get("context_truncated", False),
        ),
        can_retry=can_retry,
        created_at=reply.created_at,
        updated_at=row.finished_at or row.updated_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def read_response_snapshot(db: Session, row: Run) -> ResponseSnapshot:
    binding = require_binding(db, row)
    return ResponseSnapshot(
        conversation=read_conversation(
            db, cast(Conversation, db.get(Conversation, binding.conversation_id))
        ),
        response=read_response(db, row),
    )


def read_submission(db: Session, row: Run) -> AcceptedSubmission:
    binding = require_binding(db, row)
    return AcceptedSubmission(
        **read_response_snapshot(db, row).model_dump(),
        client_request_id=row.client_request_id,
        input_message=read_user(cast(Message, db.get(Message, binding.input_message_id)), db),
    )


def require_response(db: Session, actor: Actor, conversation_id: str, response_id: str) -> Run:
    require_conversation(db, conversation_id, actor)
    binding = db.scalar(
        select(ConversationRun).where(
            ConversationRun.conversation_id == conversation_id,
            ConversationRun.reply_message_id == response_id,
        )
    )
    if not binding:
        raise NotFoundError("response_not_found", "回复不存在。")
    return cast(Run, db.get(Run, binding.run_id))


def select_context(
    db: Session, conversation_id: str, *, context_pairs: int, context_bytes: int, size: int
) -> tuple[list[InputMessage], bool]:
    reply_alias = aliased(Message)
    successes = list(
        db.execute(
            select(ConversationRun, Message, reply_alias)
            .join(Run, Run.id == ConversationRun.run_id)
            .join(Message, Message.id == ConversationRun.input_message_id)
            .join(reply_alias, reply_alias.id == ConversationRun.reply_message_id)
            .where(ConversationRun.conversation_id == conversation_id, Run.status == "succeeded")
            .order_by(reply_alias.sequence.desc())
            .limit(context_pairs + 1)
        )
    )
    pairs: list[list[InputMessage]] = []
    for binding, user, reply in successes[:context_pairs]:
        if user.body is None or reply.body is None:
            raise ValueError("成功问答缺少正文。")
        pair_size = len(user.body.encode()) + len(reply.body.encode())
        if size + pair_size > context_bytes:
            break
        pairs.append(
            [
                {"id": user.id, "role": "user", "content": user.body},
                {"id": binding.reply_message_id, "role": "assistant", "content": reply.body},
            ]
        )
        size += pair_size
    return [message for pair in reversed(pairs) for message in pair], len(successes) > len(pairs)


def context_sources(
    db: Session, conversation_id: str, messages: list[InputMessage]
) -> list[tuple[str, str]]:
    """Only the host can connect a selected assistant message to its successful Run."""
    ids = [item["id"] for item in messages if item["role"] == "assistant"]
    runs = dict(
        db.execute(
            select(ConversationRun.reply_message_id, ConversationRun.run_id)
            .join(Run, Run.id == ConversationRun.run_id)
            .where(
                ConversationRun.conversation_id == conversation_id,
                ConversationRun.reply_message_id.in_(ids),
                Run.status == "succeeded",
            )
        ).all()
    )
    return [(runs[item["id"]], item["content"]) for item in messages if item["id"] in runs]


def read_conversation(db: Session, row: Conversation) -> ConversationRead:
    return ConversationRead(
        id=row.id,
        agent_id=row.agent_id,
        agent_name=cast(Agent, db.get(Agent, row.agent_id)).name,
        owner_user_id=row.owner_user_id,
        title=row.title,
        version=row.revision,
        last_response_id=db.scalar(
            select(ConversationRun.reply_message_id)
            .join(Message, Message.id == ConversationRun.reply_message_id)
            .where(ConversationRun.conversation_id == row.id)
            .order_by(Message.sequence.desc())
            .limit(1)
        ),
        active_response_id=db.scalar(
            select(ConversationRun.reply_message_id).where(
                ConversationRun.conversation_id == row.id, ConversationRun.active.is_(True)
            )
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def preview_text(text: str) -> str:
    """Lightweight plain-text excerpt, not a generated summary or Markdown render."""
    text = re.sub(r"^\s{0,3}(?:#{1,6}|>|[-*])\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*\*|__|`)(.*?)\1", r"\2", text)
    return " ".join(text.split())[:480]


class ConversationQueries:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(
        self, actor: Actor, agent_id: str | None = None, offset: int = 0, limit: int = 20
    ) -> Page[ConversationRead]:
        require_permission(actor, "conversations:read")
        conditions = []
        if "resources:all" not in permissions_for(actor):
            conditions.append(Conversation.owner_user_id == actor.user_id)
        if agent_id:
            conditions.append(Conversation.agent_id == agent_id)
        with self.database.transaction() as db:
            total = db.scalar(select(func.count()).select_from(Conversation).where(*conditions))
            rows = db.scalars(
                select(Conversation)
                .where(*conditions)
                .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return Page(
                items=[read_conversation(db, row) for row in rows],
                total=cast(int, total),
                offset=offset,
                limit=limit,
            )

    def get(self, actor: Actor, id: str) -> ConversationRead:
        require_permission(actor, "conversations:read")
        with self.database.transaction() as db:
            return read_conversation(db, require_conversation(db, id, actor))

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
        require_permission(actor, "conversations:read")
        if after is not None and start_number is not None:
            raise InvalidInputError("question_cursor_conflict", "只能选择一种问题定位方式。")
        with self.database.transaction() as db:
            require_conversation(db, id, actor)
            # 先编号再搜索/翻页，过滤不会改变问题的原始轮次；重试没有新输入。
            questions = (
                select(
                    Message.id.label("id"),
                    Message.sequence.label("sequence"),
                    Message.body.label("text"),
                    Message.created_at.label("created_at"),
                    func.row_number().over(order_by=Message.sequence).label("number"),
                )
                .where(Message.conversation_id == id, Message.role == "user")
                .subquery()
            )
            query = select(questions)
            if q.strip():
                query = query.where(questions.c.text.contains(q.strip(), autoescape=True))
            total = db.scalar(select(func.count()).select_from(query.subquery()))
            if after is not None:
                query = query.where(questions.c.sequence > after)
            if start_number is not None:
                query = query.where(questions.c.number >= start_number)
            rows = db.execute(query.order_by(questions.c.sequence).limit(limit + 1)).all()
            anchored = (
                db.execute(select(questions).where(questions.c.id == anchor)).first()
                if anchor
                else None
            )
            return QuestionPage(
                items=[
                    QuestionRead(
                        id=row.id,
                        sequence=row.sequence,
                        number=row.number,
                        preview=" ".join(row.text.split())[:160],
                        created_at=row.created_at,
                    )
                    for row in rows[:limit]
                ],
                total=cast(int, total),
                next_after_sequence=rows[limit - 1].sequence if len(rows) > limit else None,
                # 锚点独立于搜索与当前页，长历史无需逐页请求才能知道当前轮次。
                anchor=QuestionRead(
                    id=anchored.id,
                    sequence=anchored.sequence,
                    number=anchored.number,
                    preview=" ".join(anchored.text.split())[:160],
                    created_at=anchored.created_at,
                )
                if anchored
                else None,
            )

    def question_preview(self, actor: Actor, id: str, question_id: str) -> QuestionPreviewRead:
        require_permission(actor, "conversations:read")
        with self.database.transaction() as db:
            require_conversation(db, id, actor)
            require_permission(actor, "runs:read")
            # 重试共用输入 ID，直接选最新输出；不能从截断消息窗口猜最新回答。
            row = db.scalar(
                select(Run)
                .join(ConversationRun, ConversationRun.run_id == Run.id)
                .join(Message, Message.id == ConversationRun.reply_message_id)
                .where(
                    ConversationRun.conversation_id == id,
                    ConversationRun.input_message_id == question_id,
                )
                .order_by(Message.sequence.desc())
                .limit(1)
            )
            if row is None:
                raise NotFoundError("question_not_found", "问题不存在。")
            return QuestionPreviewRead(
                question_id=question_id,
                question=preview_text(
                    cast(
                        str,
                        cast(
                            Message, db.get(Message, require_binding(db, row).input_message_id)
                        ).body,
                    )
                ),
                answer=preview_text(read_run_content(db, row)),
                response_id=require_binding(db, row).reply_message_id,
                version=row.revision,
                status=row.status,
            )

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
        require_permission(actor, "conversations:read")
        if sum(value is not None for value in (before, after, around)) > 1:
            raise InvalidInputError("message_cursor_conflict", "只能选择一种消息定位方式。")
        if db is None:
            with self.database.transaction() as session:
                return self.messages(actor, id, before, limit, after, around, session)
        require_conversation(db, id, actor)
        require_permission(actor, "runs:read")
        # 只对业务引用分页，截取窗口后才读取正文。原始输入仅出现一次，
        # 避免大量重试挤掉旧输入，也避免跨页定位遍历中间 checkpoint。
        refs = (
            select(ConversationRun.run_id, Message.id, Message.sequence, Message.role)
            .outerjoin(ConversationRun, ConversationRun.reply_message_id == Message.id)
            .where(Message.conversation_id == id)
            .subquery()
        )
        query = select(refs)
        if around is not None:
            target = db.scalar(select(refs.c.sequence).where(refs.c.id == around))
            if target is None:
                raise NotFoundError("message_not_found", "问题或消息不存在。")
            earlier = db.execute(
                query.where(refs.c.sequence < target)
                .order_by(refs.c.sequence.desc())
                .limit(min(10, (limit - 1) // 2))
            ).all()
            later = db.execute(
                query.where(refs.c.sequence >= target)
                .order_by(refs.c.sequence)
                .limit(limit - len(earlier))
            ).all()
            selected = list(reversed(earlier)) + list(later)
        elif after is not None:
            selected = list(
                db.execute(
                    query.where(refs.c.sequence > after).order_by(refs.c.sequence).limit(limit)
                ).all()
            )
        else:
            if before is not None:
                query = query.where(refs.c.sequence < before)
            selected = list(
                reversed(db.execute(query.order_by(refs.c.sequence.desc()).limit(limit)).all())
            )
        if not selected:
            return MessagePage(items=[], next_before_sequence=None, has_more=False)
        older = (
            db.scalar(
                select(refs.c.id)
                .where(
                    refs.c.sequence < selected[0].sequence,
                )
                .limit(1)
            )
            is not None
        )
        newer = (
            db.scalar(
                select(refs.c.id)
                .where(
                    refs.c.sequence > selected[-1].sequence,
                )
                .limit(1)
            )
            is not None
        )
        run_ids = {ref.run_id for ref in selected if ref.run_id is not None}
        rows = {row.id: row for row in db.scalars(select(Run).where(Run.id.in_(run_ids)))}
        # 仅加载当前助手消息页的步骤，整页共用一次查询；正文和步骤属于同一读事务。
        assistant_ids = {ref.run_id for ref in selected if ref.role == "assistant"}
        steps_by_run: dict[str, list[RunAction]] = {run_id: [] for run_id in assistant_ids}
        if assistant_ids:
            for step in db.scalars(
                select(RunAction)
                .where(RunAction.run_id.in_(assistant_ids))
                .order_by(RunAction.run_id, RunAction.sequence)
            ):
                steps_by_run[step.run_id].append(step)
        items: list[UserMessageView | AssistantMessageView] = []
        for ref in selected:
            if ref.role == "user":
                items.append(read_user(cast(Message, db.get(Message, ref.id)), db))
            else:
                items.append(read_response(db, rows[ref.run_id], actions=steps_by_run[ref.run_id]))
        return MessagePage(
            items=items,
            next_before_sequence=selected[0].sequence if older else None,
            next_after_sequence=selected[-1].sequence if newer else None,
            has_more=older,
        )

    def response(self, actor: Actor, conversation_id: str, response_id: str) -> ResponseSnapshot:
        require_permission(actor, "runs:read")
        with self.database.transaction() as db:
            return read_response_snapshot(
                db, require_response(db, actor, conversation_id, response_id)
            )

    def snapshot(self, actor: Actor, id: str, limit: int = 50) -> ConversationSnapshot:
        require_permission(actor, "conversations:read")
        with self.database.transaction() as db:
            conversation = require_conversation(db, id, actor)
            agent = cast(Agent, db.get(Agent, conversation.agent_id))
            return ConversationSnapshot(
                conversation=read_conversation(db, conversation),
                agent={"id": agent.id, "name": agent.name, "avatar_id": agent.avatar_id},
                messages=self.messages(actor, id, limit=limit, db=db),
                question_count=cast(
                    int,
                    db.scalar(
                        select(func.count())
                        .select_from(Message)
                        .where(Message.conversation_id == id, Message.role == "user")
                    ),
                ),
                latest_question_id=db.scalar(
                    select(Message.id)
                    .where(Message.conversation_id == id, Message.role == "user")
                    .order_by(Message.sequence.desc())
                    .limit(1)
                ),
            )

    def find_request(
        self, actor: Actor, conversation_id: str, request_id: str
    ) -> AcceptedSubmission | None:
        require_permission(actor, "runs:read")
        with self.database.transaction() as db:
            require_conversation(db, conversation_id, actor)
            row = db.scalar(
                select(Run)
                .join(ConversationRun, ConversationRun.run_id == Run.id)
                .where(
                    ConversationRun.conversation_id == conversation_id,
                    Run.initiated_by_user_id == actor.user_id,
                    Run.client_request_id == request_id,
                )
            )
            return read_submission(db, row) if row else None


def read_run_content(db: Session, row: Run) -> str:
    return read_response(db, row).content
