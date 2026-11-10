from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections.abc import Awaitable, Callable, Coroutine
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SQLAlchemyError

from app.common.errors import CodedFailure
from app.common.values import utc_now
from app.infrastructure.concurrency import run_sync, settle
from app.infrastructure.observability import correlate_run, failure_frames
from app.runtime.contracts.agent import AgentContext, AgentOutput, AgentRequest, CheckpointReader
from app.runtime.contracts.runs import SUPPORTED_SNAPSHOT_VERSIONS, Completion
from app.runtime.contracts.tools import SandboxAccess, ToolCaller
from app.runtime.execution.config import RuntimeConfig
from app.runtime.execution.context import RunContext
from app.runtime.execution.errors import (
    ExecutionFailure,
    PersistenceFailure,
    execution_failure,
    terminal_status,
)
from app.runtime.execution.preparation import prepare_run

if TYPE_CHECKING:
    from app.resources.environments.service import SandboxService
    from app.resources.files.service import FileService
    from app.resources.mcp.invocation import ToolInvocationService
    from app.resources.model_connections.service import ModelConnectionService
    from app.resources.skills.service import SkillService
    from app.runtime.execution.knowledge import RunKnowledgeSearch
    from app.runtime.execution.models import Run
    from app.runtime.execution.service import RunService
    from app.runtime.execution.store import RunStore

logger = logging.getLogger(__name__)


def truncate(text: str, limit: int) -> str:
    return text.encode()[:limit].decode(errors="ignore")


class RunTask:
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
        checkpoints: CheckpointReader,
        tools: ToolInvocationService,
        files: FileService,
        sandboxes: SandboxService,
        skills: SkillService,
        knowledge: RunKnowledgeSearch,
    ) -> None:
        self.run_id, self._store, self._runs = run_id, store, runs
        self.row: Run | None = None
        self._complete, self._settings, self._agent = complete, settings, agent
        self._connections, self._checkpoints = connections, checkpoints
        self._tool_service, self._files, self._sandboxes = tools, files, sandboxes
        self._skills, self._knowledge = skills, knowledge
        self._tools: ToolCaller | None = None
        self.sandbox: SandboxAccess | None = None
        self.context: RunContext | None = None
        self.request: AgentRequest | None = None

    @correlate_run
    async def execute(self) -> None:
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
                    assert self.request is not None and self.context is not None
                    execution = asyncio.create_task(self._agent(self.request, self.context))
                    watcher = asyncio.create_task(self._watch())
                    try:
                        done, _ = await asyncio.wait(
                            (execution, watcher), return_when=asyncio.FIRST_COMPLETED
                        )
                        # 同时完成时，持久停止或存储故障优先于模型成功。
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
                        await self.context.guard()
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
            # 资源关闭后再由调度器重试持久化故障。
            storage_failed = True
            raise
        except Exception as error:
            failure = execution_failure(error)
            code = failure.code
            status = terminal_status(code)
            if isinstance(error, CodedFailure):
                text = failure.partial_text or ""
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
            progress = self.context.progress.pending() if self.context is not None else []
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
        assert self.context is not None
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
                await self.context.guard()
                last_auth = now
            if now - last_flush >= self._settings.flush_interval:
                await self.context.flush()
                last_flush = now
            await asyncio.sleep(min(self._settings.poll_interval, self._settings.flush_interval))

    async def __aenter__(self) -> RunTask:
        # 取消不会停止准备线程，须等待资源到齐再清理，包括进入失败的情况。
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
            # 清理失败不得将可恢复的停服取消改成终态失败。
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
        prepare_run(self)
