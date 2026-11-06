"""Execute one Run, supervise its work and own every acquired resource."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections.abc import Awaitable, Callable, Coroutine, Iterable
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.exc import SQLAlchemyError

from app.execution.config import RuntimeConfig
from app.execution.contracts import (
    SUPPORTED_SNAPSHOT_VERSIONS,
    AgentContext,
    AgentOutput,
    AgentRequest,
    AgentSnapshot,
    Completion,
    ContentUpdate,
    SandboxAccess,
    ToolCaller,
    ToolInvocation,
    ToolOutcome,
    ToolPermit,
    validate_snapshot,
)
from app.execution.errors import (
    ERROR_MESSAGES,
    ExecutionFailure,
    PersistenceFailure,
    terminal_status,
)
from app.execution.prompts import server_instructions, tool_instructions
from app.execution.runtime.concurrency import run_sync, settle
from app.execution.runtime.tool_results import ToolResults
from app.infrastructure.observability import correlate_run, failure_frames
from app.values import utc_now

if TYPE_CHECKING:
    from app.environments.service import SandboxService
    from app.execution.models import Run
    from app.execution.runtime.checkpoints import CheckpointStore
    from app.execution.service import RunService
    from app.execution.store import RunStore
    from app.files.service import FileService
    from app.knowledge.service import KnowledgeService
    from app.mcp.invocation import ToolInvocationService
    from app.model_connections.service import ModelConnectionService
    from app.skills.service import SkillService

logger = logging.getLogger(__name__)


def truncate(text: str, limit: int) -> str:
    return text.encode()[:limit].decode(errors="ignore")


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


class RunTask:
    """Own one execution from claiming its Run through cleanup and completion."""

    def __init__(
        self,
        run_id: str,
        complete: Callable[[Completion], Awaitable[None]],
        *,
        store: RunStore,
        runs: RunService,
        settings: RuntimeConfig,
        agent: Callable[[AgentRequest, AgentContext], Coroutine[Any, Any, AgentOutput]],
        connections: ModelConnectionService,
        checkpoints: CheckpointStore,
        tools: ToolInvocationService,
        files: FileService,
        sandboxes: SandboxService,
        skills: SkillService,
        knowledge: KnowledgeService,
    ) -> None:
        self.run_id, self._store, self._runs = run_id, store, runs
        self.row: Run | None = None
        self._complete, self._settings, self._agent = complete, settings, agent
        self._connections, self._checkpoints = connections, checkpoints
        self._tool_service, self._files, self._sandboxes = tools, files, sandboxes
        self._skills, self._knowledge = skills, knowledge
        self._tools: ToolCaller | None = None
        self.sandbox: SandboxAccess | None = None
        self.progress = _ProgressBuffer()
        self.action_skills: dict[str, tuple[str, str | None]] = {}
        self.active_skills: set[str] = set()
        self.action_keys: dict[str, str] = {}
        self.recovered_usage = None
        self.request: AgentRequest | None = None

    @correlate_run
    async def execute(self) -> None:
        """Claim, execute and close this Run before submitting its final outcome."""
        run_id = self.run_id
        storage_failed = False
        text = ""
        usage = structured = None
        status = "failed"
        code: str | None = "execution_failed"
        finish, resumable = True, False
        try:
            row, _ = await run_sync(self._store.load, run_id)
            self.row = row
            if row.config_snapshot.get("schema_version") not in SUPPORTED_SNAPSHOT_VERSIONS:
                raise ExecutionFailure("runtime_interrupted")
            resumable = row.config_snapshot.get("checkpoint_resumable", False)
            remaining = row.config_snapshot["run_timeout"]
            if row.started_at:
                remaining -= (utc_now() - row.started_at).total_seconds()
            async with asyncio.timeout(max(0, remaining)):
                await run_sync(self._runs.authorize, row)
                if not await run_sync(self._store.claim, run_id):
                    finish = False
                    return
                logger.info("execution.started run=%s", run_id)
                async with self:
                    assert self.request is not None
                    execution = asyncio.create_task(self._agent(self.request, self))
                    watcher = asyncio.create_task(self._watch())
                    try:
                        done, _ = await asyncio.wait(
                            (execution, watcher), return_when=asyncio.FIRST_COMPLETED
                        )
                        # Persisted stop/storage failures win even if the agent finishes together.
                        if watcher in done:
                            await watcher
                        result = await execution
                        if not result.text.strip():
                            raise ExecutionFailure("empty_response")
                        if len(result.text.encode()) > row.config_snapshot["max_output_bytes"]:
                            raise ExecutionFailure(
                                "output_limit_exceeded",
                                truncate(result.text, row.config_snapshot["max_output_bytes"]),
                            )
                        await self.guard()
                        text, usage, structured = (
                            result.text,
                            result.usage,
                            result.structured_result,
                        )
                    finally:
                        for task in (execution, watcher):
                            if not task.done():
                                task.cancel()
                        await asyncio.gather(execution, watcher, return_exceptions=True)
                status, code = "succeeded", None
        except asyncio.CancelledError:
            status, code = "interrupted", "runtime_interrupted"
            if resumable:
                finish = False
            raise
        except (SQLAlchemyError, sqlite3.Error, PersistenceFailure):
            # The coordinator retries persistence failures after the task has closed.
            storage_failed = True
            raise
        except Exception as error:
            code = (
                "run_timeout"
                if isinstance(error, TimeoutError)
                else getattr(error, "code", "execution_failed")
            )
            if not isinstance(code, str) or (
                code not in ERROR_MESSAGES and code != "user_cancelled"
            ):
                code = "execution_failed"
            status = terminal_status(code)
            if isinstance(error, ExecutionFailure):
                text = error.partial_text or ""
            if code == "execution_failed":
                logger.error(
                    "execution.failed",
                    extra={
                        "error_type": type(error).__name__,
                        "error_code": code,
                        "failure_frames": failure_frames(error),
                    },
                )
        finally:
            progress = self.progress.pending()
            if not finish and progress:
                try:
                    await run_sync(self._store.update_progress, run_id, progress)
                except (SQLAlchemyError, sqlite3.Error, PersistenceFailure):
                    pass
            if finish and not storage_failed:
                try:
                    await self._complete(
                        Completion(
                            run_id,
                            text,
                            status,
                            error=None if code == "user_cancelled" else code,
                            usage=usage,
                            structured=structured,
                            progress=tuple(progress),
                        )
                    )
                    logger.info(
                        "execution.finished",
                        extra={"error_code": None if status == "succeeded" else code},
                    )
                except (SQLAlchemyError, sqlite3.Error, PersistenceFailure):
                    logger.warning(
                        "execution.persistence_failed",
                        extra={"error_code": "persistence_unavailable"},
                    )

    async def _watch(self) -> None:
        last_state = last_auth = last_flush = 0.0
        while True:
            now = time.monotonic()
            if now - last_state >= self._settings.poll_interval:
                state, _ = await run_sync(self._store.state, self.run_id)
                if state != "running":
                    raise ExecutionFailure(
                        "user_cancelled" if state == "cancelling" else "runtime_interrupted"
                    )
                last_state = now
            if now - last_auth >= self._settings.auth_interval:
                await self.guard()
                last_auth = now
            if now - last_flush >= self._settings.flush_interval:
                await self.flush()
                last_flush = now
            await asyncio.sleep(min(self._settings.poll_interval, self._settings.flush_interval))

    @property
    def tools(self) -> ToolCaller:
        if self._tools is None:
            raise ExecutionFailure("runtime_interrupted")
        return self._tools

    async def __aenter__(self) -> RunTask:
        # Cancelling to_thread never stops its worker. Join it before cleanup, even
        # when entry fails, so resources cannot arrive after this context is closed.
        preparation = asyncio.create_task(asyncio.to_thread(self._prepare))
        try:
            await asyncio.shield(preparation)
        except BaseException:
            await settle(preparation)
            try:
                await self._close()
            except Exception as error:
                logger.warning("run_task.cleanup_failed type=%s", type(error).__name__)
            raise
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            await self._close()
        except Exception as error:
            if exc is None:
                raise
            # A failed close must not turn a recoverable shutdown into a terminal run.
            logger.warning("run_task.cleanup_failed type=%s", type(error).__name__)

    async def _close(self) -> None:
        async def release() -> None:
            try:
                if self.sandbox is not None:
                    await run_sync(self.sandbox.release)
            finally:
                if self._tools is not None:
                    await self._tools.aclose()

        cleanup = asyncio.create_task(release())
        try:
            await asyncio.shield(cleanup)
        except BaseException:
            await settle(cleanup)
            raise

    def _prepare(self) -> None:
        if self.row is None:
            self.row, _ = self._store.load(self.run_id)
        row = self.row
        if row.config_snapshot.get("schema_version") not in SUPPORTED_SNAPSHOT_VERSIONS:
            raise ExecutionFailure("checkpoint_unavailable")
        checkpoint = self._checkpoints.for_run(row.id, row.checkpoint_id, thread_id=row.thread_id)
        if row.model_calls and checkpoint is None:
            raise ExecutionFailure("checkpoint_unavailable")
        snapshot = cast(AgentSnapshot, dict(validate_snapshot(row.config_snapshot)))
        snapshot["system_prompt"] += tool_instructions(snapshot) + server_instructions(snapshot)
        config = self._connections.resolve(
            snapshot["connection_id"],
            snapshot["connection_config_revision"],
            snapshot["connection_credential_revision"],
        )
        self._tools = self._tool_service.for_run(row.id)
        if snapshot.get("workspace", {}).get("mode") == "sandbox":
            self.sandbox = self._sandboxes.for_run(
                row.id, snapshot.get("input_files", []), self._files.read
            )
        self._results = ToolResults(snapshot, self)
        self.restore(self._store.restore_control(row.id))
        self.request = AgentRequest(
            row.id,
            snapshot,
            row.input_snapshot,
            config,
            checkpoint,
            recovered_usage=self.recovered_usage,
            activated_skills=frozenset(self.active_skills),
            recovered_content=tuple(self.progress.contents.values()),
            thread_id=row.thread_id,
            base_checkpoint_id=row.base_checkpoint_id,
            base_run_id=row.base_run_id,
        )

    def authorize(self, active: Any = (), db: Any = None, invocation: Any = None) -> Any:
        assert self.row is not None
        return self._runs.authorize(
            self.row,
            active,
            db=db,
            **({"invocation": invocation} if invocation is not None else {}),
        )

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

    def knowledge_call(self, name: str, arguments: dict) -> ToolOutcome:
        return cast(ToolOutcome, self._knowledge.retrieval.call(self.run_id, name, arguments))

    async def preserve_tool_result(
        self, invocation: ToolInvocation, data: dict, status: str
    ) -> tuple:
        return cast(tuple, await self._results.preserve(invocation, data, status))

    def load_tool_result(self, identifier: str) -> dict:
        return self._results.load(identifier)

    def read_tool_result(self, result_id: str, offset: int = 0, limit: int = 6000) -> str:
        return self._results.read_page(result_id, offset, limit)

    def verify_web_reads(self, content: str, observations: list) -> None:
        self._results.verify_web_reads(content, observations)

    def clean_history(self, content: str) -> str:
        assert self.row is not None
        return cast(
            str,
            self._knowledge.evidence.clean_history(
                content, self.row.config_snapshot.get("knowledge", {}).get("history_evidence", [])
            ),
        )

    async def start_model(self) -> tuple[int, str]:
        return await run_sync(
            self._store.start_model, self.run_id, lambda db: self.authorize(self.active_skills, db)
        )

    async def capture_evidence(self, key: str, direction: str, stage: str, payload: dict) -> None:
        from app.execution.evidence import document

        try:
            await run_sync(
                self._store.save_evidence,
                self.run_id,
                self.action_keys.get(key, key),
                direction,
                document(stage, payload),
            )
        except Exception:
            # Evidence has its own quota and is diagnostic; its failure must not
            # replace the existing action outcome or block a model/tool operation.
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
        from app.errors import ServiceError

        try:
            permit = await run_sync(
                self._store.begin_tool,
                self.run_id,
                invocation,
                lambda db: self.authorize(self.active_skills, db, invocation=invocation),
            )
        except (ServiceError, ExecutionFailure) as error:
            try:
                await run_sync(self._store.reject_tool, self.run_id, invocation, error.code)
            except Exception:
                logger.warning("evidence.rejection_failed", extra={"action_key": invocation.key})
            raise
        self.action_keys[invocation.key] = permit.action_key
        if permit.cached is None:
            await self.capture_evidence(
                permit.action_key,
                "request",
                "tool_request",
                {
                    "name": invocation.name,
                    "requested_arguments": invocation.arguments,
                    "authorization_status": "allowed",
                },
            )
        logger.info("tool.started", extra={"action_key": permit.action_key})
        return permit

    async def guard_tool(self, invocation: ToolInvocation) -> None:
        await self.guard()
        await run_sync(self.authorize, self.active_skills, invocation=invocation)

    async def complete_tool(self, permit: ToolPermit, outcome: ToolOutcome) -> None:
        await self.capture_evidence(
            permit.action_key,
            "response",
            "tool_response",
            {
                "content": outcome.content,
                "status": outcome.status,
                "data": outcome.data,
                "sources": list(outcome.sources),
            },
        )
        await run_sync(
            self._store.finish_action,
            self.run_id,
            permit.action_key,
            outcome.status,
            "tool_upstream_failed" if outcome.status == "failed" else None,
            {
                "result_bytes": len(outcome.content.encode()),
                "sources": list(outcome.sources),
                "result_file_id": outcome.data.get("file_id"),
                "query": str(outcome.data.get("query") or "")[:2048],
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
                "error_code": "tool_upstream_failed" if outcome.status == "failed" else None,
            },
        )

    async def flush(self) -> None:
        pending = self.progress.pending()
        if pending:
            await run_sync(self._store.update_progress, self.run_id, pending)
            self.progress.acknowledge(pending)
