"""Lifespan-owned queue and task supervision; browsers only observe persisted work."""

import asyncio
import fcntl
import logging
import os
import sqlite3

from sqlalchemy.exc import SQLAlchemyError

from app.execution.contracts import Completion
from app.infrastructure.database.fields import utc_now

logger = logging.getLogger(__name__)


class Runner:
    def __init__(self, store, coordinator, settings, status, lock_path):
        self.store, self.coordinator, self.settings, self.status = (
            store,
            coordinator,
            settings,
            status,
        )
        self.lock_path = lock_path
        self.tasks = {}
        self.loop_task = None
        self.lock_file = None

    async def start(self):
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
            for intent in await asyncio.to_thread(self.store.recover, True):
                await asyncio.to_thread(self.coordinator.publish, intent)
            self.loop_task = asyncio.create_task(self._loop())
            self.loop_task.add_done_callback(self._loop_finished)
            self.status.phase = "ready"
        except BaseException:
            self.status.phase = "failed"
            self.lock_file.close()
            self.lock_file = None
            raise

    def _loop_finished(self, task):
        if self.status.phase != "stopping":
            self.status.phase = "failed"
            if not task.cancelled():
                error = task.exception()
                logger.error("Runtime scanner stopped type=%s", type(error).__name__)

    def _execution_finished(self, run_id, task):
        self.tasks.pop(run_id, None)
        if not task.cancelled() and (error := task.exception()):
            self.status.phase = "failed"
            logger.error("Runtime task stopped run=%s type=%s", run_id, type(error).__name__)

    async def stop(self):
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

    async def _loop(self):
        while True:
            try:
                for run_id in list(self.coordinator.pending_failures):
                    await asyncio.to_thread(
                        self.coordinator.publish,
                        Completion(
                            run_id=run_id,
                            content=None,
                            status="failed",
                            error="persistence_unavailable",
                        ),
                    )
                    self.coordinator.pending_failures.discard(run_id)
                queued = await asyncio.to_thread(self.store.queued_metadata)
                if not self.coordinator.pending_failures and self.status.phase in (
                    "ready",
                    "degraded",
                ):
                    self.status.phase = "ready"
                for run_id, created_at in queued:
                    if (
                        created_at
                        and (utc_now() - created_at).total_seconds() > self.settings.queue_timeout
                    ):
                        await asyncio.to_thread(
                            self.coordinator.publish,
                            Completion(
                                run_id=run_id, content=None, status="failed", error="queue_timeout"
                            ),
                        )
                    elif (
                        self.status.accepting
                        and len(self.tasks) < self.settings.concurrency
                        and run_id not in self.tasks
                    ):
                        task = asyncio.create_task(self.coordinator.run(run_id))
                        self.tasks[run_id] = task
                        task.add_done_callback(
                            lambda task, key=run_id: self._execution_finished(key, task)
                        )
            except (SQLAlchemyError, sqlite3.Error):
                self.status.phase = "degraded"
            await asyncio.sleep(self.settings.poll_interval)
