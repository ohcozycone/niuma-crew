from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, cast

from app.infrastructure.concurrency import run_sync
from app.runtime.contracts.content import ContentUpdate, KnowledgeResult
from app.runtime.contracts.tools import (
    ModelExposure,
    SandboxAccess,
    ToolCaller,
    ToolInvocation,
    ToolOutcome,
    ToolPermit,
)
from app.runtime.execution.errors import (
    ExecutionFailure,
    PersistenceFailure,
)
from app.runtime.execution.knowledge_evidence import KnowledgeEvidence
from app.runtime.execution.tool_results import ToolResults

if TYPE_CHECKING:
    from app.resources.files.service import FileService
    from app.resources.skills.service import SkillService
    from app.runtime.execution.knowledge import RunKnowledgeSearch
    from app.runtime.execution.models import Run
    from app.runtime.execution.service import RunService
    from app.runtime.execution.store import RunStore

logger = logging.getLogger(__name__)


class _ProgressBuffer:
    def __init__(self) -> None:
        self.contents: dict[str, ContentUpdate] = {}
        self.dirty: dict[str, ContentUpdate] = {}

    def record(self, update: ContentUpdate) -> None:
        if self.contents.get(update.key) != update:
            self.contents[update.key] = self.dirty[update.key] = update

    def pending(self) -> list[ContentUpdate]:
        return list(self.dirty.values())

    def acknowledge(self, saved: list[ContentUpdate]) -> None:
        for value in saved:
            if self.dirty.get(value.key) is value:
                self.dirty.pop(value.key)


class RunContext:
    def __init__(
        self,
        row: Run,
        *,
        store: RunStore,
        runs: RunService,
        files: FileService,
        skills: SkillService,
        knowledge: RunKnowledgeSearch,
        tools: ToolCaller | None,
        sandbox: SandboxAccess | None,
    ) -> None:
        self.row, self.run_id = row, row.id
        self._store, self._runs = store, runs
        self._files, self._skills, self._knowledge = files, skills, knowledge
        self._tools, self.sandbox = tools, sandbox
        self.progress = _ProgressBuffer()
        self.action_skills: dict[str, tuple[str, str | None]] = {}
        self.active_skills: set[str] = set()
        self.action_keys: dict[str, str] = {}
        self.recovered_usage = None
        self._results = ToolResults(row.config_snapshot, self)

    @property
    def tools(self) -> ToolCaller:
        if self._tools is None:
            raise ExecutionFailure("runtime_interrupted")
        return self._tools

    def authorize(
        self,
        active: Any = (),
        db: Any = None,
        invocation: Any = None,
        exposure: ModelExposure | None = None,
    ) -> Any:
        assert self.row is not None
        options: dict[str, Any] = {}
        if invocation is not None:
            options["invocation"] = invocation
        if exposure is not None:
            options["exposure"] = exposure
        return self._runs.authorize(self.row, active, db=db, **options)

    def read_file(self, identifier: str) -> bytes:
        return cast(bytes, self._files.read(identifier))

    def list_sources(self) -> list[dict]:
        return cast(list[dict], self._files.sources(self.run_id))

    def save_source(self, name: str, data: bytes) -> dict:
        assert self.row is not None
        return cast(
            dict,
            self._files.save(
                self.row.owner_user_id,
                name,
                data,
                purpose="source",
                run_id=self.run_id,
                media_type="text/plain; charset=utf-8",
            ),
        )

    def save_output(self, name: str, data: bytes) -> dict:
        assert self.row is not None
        return cast(
            dict,
            self._files.save(
                self.row.owner_user_id, name, data, purpose="output", run_id=self.run_id
            ),
        )

    def read_skill_blob(self, content_hash: str) -> bytes:
        return cast(bytes, self._skills.read_blob(content_hash))

    def knowledge_call(self, name: str, arguments: dict) -> KnowledgeResult:
        return cast(KnowledgeResult, self._knowledge.call(self.run_id, name, arguments))

    async def preserve_tool_result(
        self, invocation: ToolInvocation, data: dict, status: str
    ) -> tuple:
        return cast(tuple, await self._results.preserve(invocation, data, status))

    def load_tool_result(self, identifier: str) -> dict:
        self.authorize(self.active_skills)
        return self._results.load(identifier)

    def tool_result_aliases(self) -> dict:
        self.authorize(self.active_skills)
        return self._store.tool_result_aliases(self.run_id)

    def read_tool_result(self, result_id: str, offset: int = 0, limit: int = 6000) -> str:
        return self._results.read_page(result_id, offset, limit)

    def clean_history(self, content: str) -> str:
        assert self.row is not None
        return cast(
            str,
            KnowledgeEvidence.clean_history(
                content, self.row.config_snapshot.get("knowledge", {}).get("history_evidence", [])
            ),
        )

    async def remaining_model_calls(self) -> int:
        return await run_sync(self._store.remaining_model_calls, self.run_id)

    async def start_model(self, exposure: ModelExposure) -> tuple[int, str]:
        return await run_sync(
            self._store.start_model,
            self.run_id,
            lambda db: self.authorize(self.active_skills, db, exposure=exposure),
            exposure=exposure,
        )

    async def capture_evidence(self, key: str, direction: str, stage: str, payload: dict) -> None:
        from app.runtime.execution.evidence import document

        try:
            await run_sync(
                self._store.save_evidence,
                self.run_id,
                self.action_keys.get(key, key),
                direction,
                document(stage, payload),
            )
        except Exception:
            # 证据有独立配额；采集失败不覆盖原动作结果或阻断调用。
            logger.warning(
                "evidence.capture_failed",
                extra={"action_key": key, "error_code": "evidence_unavailable"},
            )

    async def guard(self, extra: Iterable[str] = ()) -> None:
        state, _ = await run_sync(self._store.state, self.run_id)
        if state != "running":
            raise ExecutionFailure(
                "user_cancelled" if state == "cancelling" else "runtime_interrupted"
            )
        await run_sync(self.authorize, self.active_skills | set(extra))

    async def start(
        self,
        key: str,
        kind: str,
        details: dict | None = None,
        skill_id: str | None = None,
        *,
        budget: str | None = None,
    ) -> None:
        await self.guard([skill_id] if skill_id else [])
        self.action_skills[key] = (kind, skill_id)
        self.action_keys[key] = await run_sync(
            self._store.start_action,
            self.run_id,
            key,
            kind,
            details,
            skill_id,
            budget=budget,
            authorize=lambda db: self.authorize(
                self.active_skills | ({skill_id} if skill_id else set()), db
            ),
        )

    async def finish(
        self,
        key: str,
        status: str = "succeeded",
        error: str | None = None,
        details: dict | None = None,
        usage: dict | None = None,
        content: ContentUpdate | None = None,
    ) -> None:
        if content is not None:
            self.progress.record(content)
        await run_sync(
            self._store.finish_action,
            self.run_id,
            self.action_keys.get(key, key),
            status,
            error,
            details,
            usage,
            content,
        )

        kind, skill_id = self.action_skills.get(key, (None, None))
        if kind == "skill_activation" and skill_id and status == "succeeded":
            self.active_skills.add(skill_id)

    def restore(self, restored: dict) -> None:
        self.active_skills.update(restored["active_skills"])
        self.progress.contents.update({item.key: item for item in restored["contents"]})
        self.recovered_usage = restored["usage"]

    async def report_content(self, update: ContentUpdate) -> None:
        self.progress.record(update)

    async def checkpoint_saved(self, reference: str) -> None:
        await run_sync(self._store.checkpoint_saved, self.run_id, reference)

    async def begin_tool(self, invocation: ToolInvocation) -> ToolPermit:
        from app.common.errors import CodedFailure, ServiceError

        try:
            permit = await run_sync(
                self._store.begin_tool,
                self.run_id,
                invocation,
                lambda db: self.authorize(self.active_skills, db, invocation=invocation),
            )
        # 存储故障不能登记为授权拒绝。
        except PersistenceFailure:
            raise
        except (ServiceError, CodedFailure) as error:
            try:
                await run_sync(self._store.reject_tool, self.run_id, invocation, error.code)
            except Exception:
                logger.warning("evidence.rejection_failed", extra={"action_key": invocation.key})
            raise
        self.action_keys[invocation.key] = permit.action_key
        logger.info("tool.started", extra={"action_key": permit.action_key})
        return permit

    async def guard_tool(self, invocation: ToolInvocation) -> None:
        await self.guard()
        await run_sync(self.authorize, self.active_skills, invocation=invocation)

    async def complete_tool(self, permit: ToolPermit, outcome: ToolOutcome) -> None:
        code = (
            None
            if outcome.status == "succeeded"
            else (
                outcome.error_code
                or outcome.data.get("code")
                or (
                    "tool_result_unknown" if outcome.status == "unknown" else "tool_upstream_failed"
                )
            )
        )
        await self.capture_evidence(
            permit.action_key,
            "response",
            "tool_response",
            {
                "content": outcome.content,
                "status": outcome.status,
                "data": outcome.data,
                "sources": list(outcome.sources),
                "error_code": code,
            },
        )
        discovery = outcome.data.get("discovery")
        summary = (
            {
                "category": "tool_discovery",
                "matched_ids": discovery["matched_ids"],
                "pending_ids": discovery["pending_ids"],
                "matched_count": len(discovery["matched_ids"]),
                "pending_count": len(discovery["pending_ids"]),
                "elapsed_ms": discovery["elapsed_ms"],
                "catalog_hash": discovery["catalog_hash"],
            }
            if discovery
            else {}
        )
        await run_sync(
            self._store.finish_action,
            self.run_id,
            permit.action_key,
            outcome.status,
            code,
            {
                "result_bytes": len(outcome.content.encode()),
                "sources": list(outcome.sources),
                "result_file_id": outcome.data.get("file_id"),
                "query": str(outcome.data.get("query") or "")[:2048],
                **summary,
            },
            result_payload={
                "content": outcome.content,
                "status": outcome.status,
                "data": outcome.data,
            },
        )

        logger.info(
            "tool.finished",
            extra={
                "action_key": permit.action_key,
                "error_code": code,
            },
        )

    async def flush(self) -> None:
        pending = self.progress.pending()
        if pending:
            await run_sync(self._store.update_progress, self.run_id, pending)
            self.progress.acknowledge(pending)
