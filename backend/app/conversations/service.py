"""Keep conversation writes and execution admission in one business transaction."""

from sqlalchemy import select

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.conversations.acceptance import ConversationAcceptance
from app.conversations.access import require_binding, require_conversation, require_response
from app.conversations.context import accepted_run_id
from app.conversations.models import Conversation, ConversationRun, Message, MessageFile
from app.conversations.queries import read_response_snapshot, read_submission
from app.conversations.schemas import AcceptedSubmission, ResponseSnapshot
from app.conversations.writes import bind_run, create_conversation, prepare_input, require_idle
from app.employees.access import configured_agent
from app.errors import ConflictError, InvalidInputError
from app.execution.config import RuntimeConfig
from app.execution.service import RunService, find_request, request_digest
from app.execution.store import require_run
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer


class ConversationService:
    def __init__(
        self,
        database: Database,
        settings: RuntimeConfig,
        runs: RunService,
        acceptance: ConversationAcceptance,
    ) -> None:
        self.database, self.settings, self.runs, self.acceptance = (
            database,
            settings,
            runs,
            acceptance,
        )

    def submit(
        self,
        actor: Actor,
        conversation_id: str | None,
        request_id: str,
        content: str | None = None,
        retry_id: str | None = None,
        selected_skill_ids: list[str] | None = None,
        agent_id: str | None = None,
        file_ids: list[str] | None = None,
    ) -> tuple[AcceptedSubmission, bool]:
        require_permission(actor, "runs:create")
        selected, selected_files = sorted(selected_skill_ids or []), sorted(file_ids or [])
        if len(selected) > 16 or len(selected) != len(set(selected)):
            raise InvalidInputError(
                "skill_selection_not_allowed", "技能选择不能重复且最多为 16 项。"
            )
        operation = (
            "conversation.create"
            if conversation_id is None
            else "conversation.retry"
            if retry_id
            else "conversation.send"
        )
        # The first-send hash retains null; never include a newly allocated conversation ID.
        digest = request_digest(
            dict(
                conversation_id=conversation_id,
                retry_id=retry_id,
                content=content,
                selected_skill_ids=selected,
                agent_id=agent_id,
                file_ids=selected_files,
            )
        )
        with self.database.transaction() as db:
            reserve_writer(db, Conversation.__table__)
            existing = find_request(db, actor, operation, request_id, digest)
            if existing is not None:
                return read_submission(db, existing), False
            if conversation_id is None:
                require_permission(actor, "conversations:create")
                if not agent_id:
                    raise InvalidInputError("agent_required", "创建对话需要选择员工。")
                configured_agent(db, agent_id)
                conversation = create_conversation(db, agent_id, actor.user_id)
            else:
                conversation = require_conversation(db, conversation_id, actor)
                if agent_id is not None and conversation.agent_id != agent_id:
                    raise ConflictError(
                        "conversation_agent_conflict", "对话关联的员工与请求不一致。"
                    )
            require_idle(db, conversation)
            previous = None
            previous_binding = None
            if retry_id:
                previous = require_run(db, retry_id, actor)
                previous_binding = require_binding(db, previous)
                latest = db.scalar(
                    select(ConversationRun.run_id)
                    .join(Message, Message.id == ConversationRun.run_id)
                    .where(ConversationRun.conversation_id == conversation.id)
                    .order_by(Message.sequence.desc())
                    .limit(1)
                )
                if (
                    previous_binding.conversation_id != conversation.id
                    or previous.status not in ("failed", "cancelled", "interrupted")
                    or latest != retry_id
                ):
                    raise ConflictError(
                        "retry_not_allowed", "只能重试当前对话的最后一次失败或停止的执行。"
                    )
                source = db.get(Message, previous_binding.input_message_id)
                if source is None or source.body is None:
                    raise ConflictError("retry_not_allowed", "重试输入不可读取。")
                content = source.body
                selected = previous.config_snapshot.get("selected_skill_ids", [])
                selected_files = [
                    item["id"] for item in previous.config_snapshot.get("input_files", [])
                ]
            if content is None or not content.strip():
                raise InvalidInputError("input_required", "请输入消息。")
            allowed_files = (
                set(
                    db.scalars(
                        select(MessageFile.file_id)
                        .join(Message, Message.id == MessageFile.message_id)
                        .where(Message.conversation_id == conversation.id)
                    )
                )
                if selected_files
                else set()
            )
            message = prepare_input(db, conversation, content, previous_binding)
            run = self.runs.submit(
                db,
                actor,
                owner_user_id=conversation.owner_user_id,
                agent_id=conversation.agent_id,
                content=content,
                input_message_id=message.id,
                selected_skill_ids=selected,
                file_ids=selected_files,
                allowed_file_ids=allowed_files,
                origin_kind="conversation",
                operation=operation,
                request_id=request_id,
                digest=digest,
                thread_id="conversation:" + conversation.id,
                base_run_id=accepted_run_id(db, conversation.id),
                retry_of=previous,
            )
            if previous_binding is None:
                for ref in run.config_snapshot.get("input_files", []):
                    db.add(MessageFile(message_id=message.id, file_id=ref["id"]))
            bind_run(db, conversation, message, run)
            return read_submission(db, run), True

    def retry(
        self, actor: Actor, conversation_id: str, response_id: str, request_id: str
    ) -> tuple[AcceptedSubmission, bool]:
        require_permission(actor, "runs:create")
        with self.database.transaction() as db:
            row = require_response(db, actor, conversation_id, response_id)
            binding = require_binding(db, row)
            require_conversation(db, binding.conversation_id, actor)
            conversation_id = binding.conversation_id
        return self.submit(actor, conversation_id, request_id, retry_id=row.id)

    def cancel(self, actor: Actor, conversation_id: str, response_id: str) -> ResponseSnapshot:
        require_permission(actor, "runs:cancel")
        with self.database.transaction() as db:
            reserve_writer(db, Conversation.__table__)
            row = require_response(db, actor, conversation_id, response_id)
            binding = require_binding(db, row)
            require_conversation(db, binding.conversation_id, actor)
            self.runs.cancel(db, row)
            run_id = row.id
        self.acceptance.process(run_id)
        with self.database.transaction() as db:
            return read_response_snapshot(db, require_run(db, run_id, actor))
