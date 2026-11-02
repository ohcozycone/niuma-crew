"""Accept communication and execution together; execute outside this transaction."""

import json

from sqlalchemy import select

from app.agents.execution_config import configured_agent
from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.conversations.models import Conversation, ConversationRun, Message, MessageFile
from app.conversations.preparation import ConversationPreparation
from app.conversations.publication import PublishRun
from app.conversations.queries import (
    context_sources,
    read_conversation,
    read_response_snapshot,
    read_submission,
    require_binding,
    require_conversation,
    require_response,
    select_context,
)
from app.conversations.schemas import AcceptedSubmission, ConversationRead, ResponseSnapshot
from app.conversations.writes import bind_run, create_conversation, prepare_input, require_idle
from app.errors import ConflictError, InvalidInputError
from app.execution.admission import RunAdmission, request_digest
from app.execution.config import RuntimeConfig
from app.execution.contracts import Completion
from app.execution.models import Run
from app.execution.queries import require_run
from app.infrastructure.database.fields import utc_now
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer


class ConversationService:
    def __init__(
        self,
        database: Database,
        settings: RuntimeConfig,
        admission: RunAdmission,
        assembler: ConversationPreparation,
        publisher: PublishRun,
    ) -> None:
        self.database, self.settings, self.admission, self.assembler, self.publisher = (
            database,
            settings,
            admission,
            assembler,
            publisher,
        )

    def create(self, actor: Actor, agent_id: str) -> ConversationRead:
        require_permission(actor, "conversations:create")
        with self.database.transaction() as db:
            reserve_writer(db, Conversation.__table__)
            configured_agent(db, agent_id)
            row = create_conversation(db, agent_id, actor.user_id)
            result = read_conversation(db, row)
        return result

    def submit(
        self,
        actor: Actor,
        conversation_id: str,
        request_id: str,
        content: str | None = None,
        retry_id: str | None = None,
        selected_skill_ids: list[str] | None = None,
        agent_id: str | None = None,
        file_ids: list[str] | None = None,
    ) -> tuple[AcceptedSubmission, bool]:
        require_permission(actor, "runs:create")
        selected = sorted(selected_skill_ids or [])
        selected_files = sorted(file_ids or [])
        if len(selected) > 16 or len(selected) != len(set(selected)):
            raise InvalidInputError(
                "skill_selection_not_allowed", "技能选择不能重复且最多为 16 项。"
            )
        operation = "conversation.retry" if retry_id else "conversation.send"
        digest = request_digest(
            dict(
                conversation_id=conversation_id,
                retry_id=retry_id,
                content=content,
                # Preserve the canonical digest of ordinary requests accepted before retirement.
                work=None,
                selected_skill_ids=selected,
                agent_id=agent_id,
                file_ids=selected_files,
            )
        )
        with self.database.transaction() as db:
            reserve_writer(db, Conversation.__table__)
            conversation = db.get(Conversation, conversation_id)
            if conversation is None and agent_id is not None:
                require_permission(actor, "conversations:create")
                configured_agent(db, agent_id)
                conversation = create_conversation(db, agent_id, actor.user_id, conversation_id)
            else:
                conversation = require_conversation(db, conversation_id, actor)
            if agent_id is not None and conversation.agent_id != agent_id:
                raise ConflictError("conversation_agent_conflict", "对话关联的员工与请求不一致。")
            existing = self.admission.replay(db, actor, operation, request_id, digest)
            if existing:
                if require_binding(db, existing).conversation_id != conversation_id:
                    raise ConflictError("idempotency_conflict", "请求归属不一致。")
                return read_submission(db, existing), False
            self.admission.check_capacity(db, actor)
            require_idle(db, conversation)
            previous: Run | None = None
            previous_binding: ConversationRun | None = None
            if retry_id:
                previous = require_run(db, retry_id, actor)
                if (
                    previous.config_snapshot.get("retired_work")
                    or previous.config_snapshot.get("work")
                    or previous.config_snapshot.get("ci")
                ):
                    raise ConflictError("retry_not_allowed", "此历史功能已移除，仅可查看原记录。")
                previous_binding = require_binding(db, previous)
                latest = db.scalar(
                    select(ConversationRun.run_id)
                    .join(Message, Message.id == ConversationRun.reply_message_id)
                    .where(ConversationRun.conversation_id == conversation_id)
                    .order_by(Message.sequence.desc())
                    .limit(1)
                )
                if (
                    previous_binding.conversation_id != conversation_id
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
            snapshot, size = self.assembler.prepare(
                db, conversation.agent_id, content, selected, user_id=actor.user_id
            )
            if snapshot.get("knowledge") and actor.user_id != conversation.owner_user_id:
                raise ConflictError(
                    "knowledge_owner_mismatch",
                    "个人知识库不能用于他人拥有的对话，请创建自己的对话。",
                )
            if selected_files:
                allowed_files = set(
                    db.scalars(
                        select(MessageFile.file_id)
                        .join(Message, Message.id == MessageFile.message_id)
                        .where(Message.conversation_id == conversation_id)
                    )
                )
                snapshot["input_files"] = self.assembler.files.capture(
                    db, selected_files, actor.user_id, allowed_ids=allowed_files
                )
                if not any(
                    item["kind"] == "native"
                    and (
                        item["tool_name"] == "execute"
                        or (
                            item["tool_name"] == "read_file"
                            and "/inputs" in item["scope_policy"].get("read_roots", [])
                        )
                    )
                    for item in snapshot.get("tools", [])
                ):
                    raise InvalidInputError(
                        "file_tool_required", "请先为员工授予输入目录的文件读取工具。"
                    )
                size += len(json.dumps(snapshot["input_files"], ensure_ascii=False).encode())
                if snapshot["workspace"]["mode"] == "virtual" and (
                    any(ref["size"] > 131072 for ref in snapshot["input_files"])
                    or sum(ref["size"] for ref in snapshot["input_files"]) > 524288
                ):
                    raise InvalidInputError(
                        "file_too_large",
                        "虚拟文本工作区仅支持单文件 128 KiB、总量 512 KiB；大文件请启用沙箱。",
                    )
            context, truncated = select_context(
                db,
                conversation_id,
                size=size,
                context_pairs=self.settings.context_pairs,
                context_bytes=self.settings.context_bytes,
            )
            snapshot["context_pair_count"], snapshot["context_truncated"] = (
                len(context) // 2,
                truncated,
            )
            if snapshot.get("knowledge"):
                knowledge = self.assembler.knowledge.context
                remaining = (
                    self.settings.context_bytes
                    - size
                    - sum(len(item["content"].encode()) for item in context)
                )
                evidence = knowledge.capture(
                    db,
                    snapshot["knowledge"],
                    context_sources(db, conversation_id, context),
                    max(0, remaining - 1024),
                )
                snapshot["knowledge"] = {**snapshot["knowledge"], "history_evidence": evidence}
            if self.assembler.knowledge:
                for item in context:
                    if item["role"] == "assistant":
                        item["content"] = self.assembler.knowledge.context.clean(
                            item["content"],
                            snapshot.get("knowledge", {}).get("history_evidence", []),
                        )
            message = prepare_input(db, conversation, content, previous_binding)
            if previous_binding is None:
                for ref in snapshot.get("input_files", []):
                    db.add(MessageFile(message_id=message.id, file_id=ref["id"]))
            run = self.admission.accept(
                db,
                actor,
                owner_user_id=conversation.owner_user_id,
                agent_id=conversation.agent_id,
                origin_kind="conversation",
                operation=operation,
                request_id=request_id,
                digest=digest,
                snapshot=snapshot,
                messages=[*context, {"id": message.id, "role": "user", "content": content}],
                retry_of=previous,
            )
            if snapshot.get("knowledge"):
                self.assembler.knowledge.context.bind(db, run)
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
            if row.status in ("queued", "running"):
                row.cancel_requested_at = utc_now()
                if row.status == "queued":
                    self.publisher.finish(db, row, Completion(row.id, None, "cancelled"))
                else:
                    row.status = "cancelling"
                    row.revision += 1
                db.flush()
            return read_response_snapshot(db, row)
