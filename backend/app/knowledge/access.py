"""Knowledge access owner, independent of SDK tool registration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import require_permission
from app.auth.work_authorizations import authorize_work
from app.employees.models import Agent
from app.errors import AuthenticationError, ConflictError, InvalidInputError, PermissionDeniedError
from app.execution.contracts import ToolInvocation
from app.execution.models import Run
from app.knowledge.contracts import TOOL_BINDINGS
from app.knowledge.models import (
    KnowledgeBase,
    RunKnowledgeEvidence,
)
from app.knowledge.schemas import (
    KnowledgeReadInput,
    KnowledgeSearchInput,
)
from app.values import utc_now

if TYPE_CHECKING:
    from app.knowledge.service import KnowledgeService


class KnowledgeAccess:
    def __init__(self, knowledge: KnowledgeService) -> None:
        self.knowledge = knowledge

    def assert_current(
        self, db: Session, snapshot: Mapping[str, Any], run_id: str | None = None
    ) -> None:
        captured = snapshot.get("knowledge")
        if not captured:
            return
        setting = self.knowledge.assignments.settings(db, captured["agent_id"], captured["user_id"])
        agent = db.get(Agent, captured["agent_id"])
        ids = {item["id"] for item in captured["libraries"]}
        if (
            snapshot.get("agent_id") != captured["agent_id"]
            or not setting
            or not agent
            or not agent.is_active
            or setting.revision != captured["revision"]
            or any(
                getattr(setting, key) != captured.get(key) for key in ("mode", "strategy", "top_k")
            )
            or set(self.knowledge.assignments.library_ids(db, setting)) != ids
        ):
            raise ConflictError(
                "knowledge_access_revoked", "个人知识库装配已变化，请重新发送任务。"
            )
        for id in ids:
            base = db.get(KnowledgeBase, id)
            if base is None or base.owner_user_id != captured["user_id"]:
                raise ConflictError("knowledge_access_revoked", "知识库已删除或不再属于当前用户。")
        if run_id:
            row = db.get(Run, run_id)
            if (
                row is None
                or row.agent_id != captured["agent_id"]
                or row.owner_user_id != captured["user_id"]
                or row.initiated_by_user_id != captured["user_id"]
            ):
                raise ConflictError(
                    "knowledge_access_revoked", "个人知识只能用于本人发起且拥有的对话。"
                )
            for evidence in db.scalars(
                select(RunKnowledgeEvidence).where(RunKnowledgeEvidence.run_id == run_id)
            ):
                self.knowledge.evidence.assert_evidence(db, evidence, ids)

    def authorize(
        self, db: Session, snapshot: Mapping[str, Any], invocation: ToolInvocation
    ) -> dict:
        self.assert_current(db, snapshot)
        if (
            not snapshot.get("knowledge")
            or TOOL_BINDINGS.get(invocation.name) != invocation.binding_id
            or not any(
                item.get("kind") == "knowledge"
                and item.get("binding_id") == invocation.binding_id
                and item.get("exposed_name") == invocation.name
                and item.get("tool_name") == invocation.name
                for item in snapshot.get("tools", [])
            )
        ):
            raise ConflictError("tool_not_allowed", "本轮没有该知识工具许可。")
        args = self.arguments(invocation.name, invocation.arguments)
        if isinstance(args, KnowledgeSearchInput) and args.library_ids:
            allowed = {item["id"] for item in snapshot["knowledge"]["libraries"]}
            if {str(id) for id in args.library_ids} - allowed:
                raise InvalidInputError("tool_not_allowed", "检索范围只能收窄已挂载的知识库。")
        return {
            "kind": "knowledge",
            "tool_name": invocation.name,
            "recovery": "readonly",
            "scope_policy": {"max_calls": 12},
        }

    @staticmethod
    def arguments(name: str, args: dict) -> KnowledgeSearchInput | KnowledgeReadInput:
        try:
            if name == "search_knowledge":
                return KnowledgeSearchInput.model_validate(args)
            if name == "read_knowledge_source":
                return KnowledgeReadInput.model_validate(args)
        except ValidationError:
            raise InvalidInputError(
                "tool_arguments_invalid", "知识工具参数无效，请检查问题、范围或证据编号。"
            ) from None
        raise ConflictError("tool_not_allowed", "没有该知识工具许可。")

    def run_scope(self, db: Session, run_id: str) -> tuple[Run, dict]:
        row = db.get(Run, run_id)
        if row is None or not row.config_snapshot.get("knowledge"):
            raise ConflictError("tool_not_allowed", "本轮没有挂载知识库。")
        self.assert_current(db, row.config_snapshot, run_id)
        if row.status != "running":
            raise ConflictError(
                "user_cancelled" if row.status == "cancelling" else "runtime_interrupted",
                "本轮已停止。",
            )
        try:
            current = authorize_work(db, row.initiated_by_user_id, row.initiated_by_session_id)
            require_permission(current, "knowledge:use")
        except (AuthenticationError, PermissionDeniedError) as error:
            raise ConflictError("actor_session_invalid", "发起工作授权已失效。") from error
        seconds = row.config_snapshot.get("run_timeout", 120)
        if row.started_at and utc_now() - row.started_at > timedelta(seconds=seconds):
            raise ConflictError("run_timeout", "知识检索超过本轮时限。")
        return row, row.config_snapshot["knowledge"]
