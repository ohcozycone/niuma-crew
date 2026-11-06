"""Coordinate durable queued work and own the process-wide task lifecycle."""

import asyncio
import fcntl
import logging
import os
import sqlite3
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from typing import IO, Any

from sqlalchemy.exc import SQLAlchemyError

from app.execution.config import RuntimeConfig
from app.execution.contracts import (
    Completion,
    ExecutionStatus,
)
from app.execution.errors import PersistenceFailure
from app.execution.runtime.concurrency import run_sync
from app.execution.runtime.task import RunTask
from app.execution.service import RunService
from app.execution.store import RunStore
from app.values import utc_now

logger = logging.getLogger(__name__)


class RunWorker:
    def __init__(
        self,
        store: RunStore,
        runs: RunService,
        task_factory: Callable[[str, Callable[[Completion], Awaitable[None]]], RunTask],
        settings: RuntimeConfig,
        status: ExecutionStatus,
        lock_path: Path,
    ) -> None:
        self.store, self.runs, self.task_factory = store, runs, task_factory
        self.settings, self.status, self.lock_path = settings, status, lock_path
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.pending_failures: set[str] = set()
        self.loop_task: asyncio.Task[None] | None = None
        self.lock_file: IO[str] | None = None
        self._notify_completion: Callable[[], None] | None = None

    def set_completion_notifier(self, notifier: Callable[[], None]) -> None:
        self._notify_completion = notifier

    async def _complete(self, intent: Completion) -> None:
        try:
            await run_sync(self.runs.complete, intent)
        except (SQLAlchemyError, sqlite3.Error, PersistenceFailure):
            self.pending_failures.add(intent.run_id)
            self.status.phase = "degraded"
            raise
        if self._notify_completion is not None:
            try:
                self._notify_completion()
            except Exception as error:
                logger.warning("completion.notification_failed type=%s", type(error).__name__)

    async def start(self) -> None:
        self.status.phase = "starting"
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = self.lock_path.open("a")
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close()
            self.lock_file = None
            raise RuntimeError("同一运行锁只允许一个后端进程运行对话服务。") from None
        try:
            os.chmod(self.lock_file.name, 0o600)
            for intent in await run_sync(self.store.recover, True):
                await self._complete(intent)
            self.loop_task = asyncio.create_task(self._loop())
            self.loop_task.add_done_callback(self._loop_finished)
            self.status.phase = "ready"
        except BaseException:
            self.status.phase = "failed"
            self.lock_file.close()
            self.lock_file = None
            raise

    def _loop_finished(self, task: Any) -> None:
        if self.status.phase != "stopping":
            self.status.phase = "failed"
            if not task.cancelled():
                error = task.exception()
                logger.error("Runtime scanner stopped type=%s", type(error).__name__)

    def _execution_finished(self, run_id: Any, task: Any) -> None:
        self.tasks.pop(run_id, None)
        if not task.cancelled() and (error := task.exception()):
            if isinstance(error, (SQLAlchemyError, sqlite3.Error, PersistenceFailure)):
                self.pending_failures.add(run_id)
                self.status.phase = "degraded"
            else:
                self.status.phase = "failed"
                logger.error("Runtime task stopped run=%s type=%s", run_id, type(error).__name__)

    async def stop(self) -> None:
        self.status.phase = "stopping"
        if self.lock_file is None:
            return
        if self.loop_task:
            self.loop_task.cancel()
            await asyncio.gather(self.loop_task, return_exceptions=True)
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.lock_file.close()
        self.lock_file = None

    async def _loop(self) -> None:
        while True:
            try:
                for run_id in list(self.pending_failures):
                    await self._complete(
                        Completion(
                            run_id=run_id,
                            content=None,
                            status="failed",
                            error="persistence_unavailable",
                        ),
                    )
                    self.pending_failures.discard(run_id)
                queued = await run_sync(self.store.queued_metadata)
                if not self.pending_failures and self.status.phase in (
                    "ready",
                    "degraded",
                ):
                    self.status.phase = "ready"
                for run_id, created_at in queued:
                    if (
                        created_at
                        and (utc_now() - created_at).total_seconds() > self.settings.queue_timeout
                    ):
                        await self._complete(
                            Completion(
                                run_id=run_id, content=None, status="failed", error="queue_timeout"
                            ),
                        )
                    elif self.status.accepting and run_id not in self.tasks:
                        work = self.task_factory(run_id, self._complete)
                        task = asyncio.create_task(work.execute())
                        self.tasks[run_id] = task
                        task.add_done_callback(partial(self._execution_finished, run_id))
            except (SQLAlchemyError, sqlite3.Error, PersistenceFailure):
                self.status.phase = "degraded"
            await asyncio.sleep(self.settings.poll_interval)
