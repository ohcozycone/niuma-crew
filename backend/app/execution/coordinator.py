"""Coordinate one run; execution and observation have one terminal decision."""

import asyncio
import logging
import sqlite3
import time

from sqlalchemy.exc import SQLAlchemyError

from app.execution.contracts import (
    SUPPORTED_SNAPSHOT_VERSIONS,
    Completion,
    ExecutionStatus,
)
from app.execution.control import RunControl, truncate
from app.execution.errors import (
    ERROR_MESSAGES,
    ExecutionFailure,
    PublicationFailure,
    terminal_status,
)
from app.infrastructure.database.fields import utc_now

logger = logging.getLogger(__name__)


class ExecutionCoordinator:
    def __init__(
        self,
        store,
        prepare,
        authorize,
        publish,
        settings,
        status: ExecutionStatus,
    ):
        self.store, self.prepare, self.authorize, self.publish = store, prepare, authorize, publish
        self.settings, self.status = settings, status
        self.pending_failures: set[str] = set()

    async def _watch(self, input, hooks):
        last_state = last_auth = last_flush = 0
        while True:
            now = time.monotonic()
            if now - last_state >= self.settings.poll_interval:
                state, _ = await asyncio.to_thread(self.store.state, input.id)
                if state != "running":
                    raise ExecutionFailure(
                        "user_cancelled" if state == "cancelling" else "runtime_interrupted"
                    )
                last_state = now
            if now - last_auth >= self.settings.auth_interval:
                await hooks.guard()
                last_auth = now
            if now - last_flush >= self.settings.flush_interval:
                await hooks.flush()
                last_flush = now
            await asyncio.sleep(min(self.settings.poll_interval, self.settings.flush_interval))

    async def run(self, run_id: str):
        execution = watcher = None
        hooks = None
        plan = None
        text = ""
        usage = structured = None
        status, code = "failed", "execution_failed"
        finish = True
        resumable = False
        try:
            row, messages = await asyncio.to_thread(self.store.load, run_id)
            if row.config_snapshot.get("schema_version") not in SUPPORTED_SNAPSHOT_VERSIONS:
                raise ExecutionFailure("runtime_interrupted")
            resumable = row.config_snapshot.get("checkpoint_resumable", False)
            remaining = row.config_snapshot["run_timeout"]
            if row.started_at:
                remaining -= (utc_now() - row.started_at).total_seconds()
            async with asyncio.timeout(max(0, remaining)):
                await asyncio.to_thread(self.authorize, row)
                if not await asyncio.to_thread(self.store.claim, run_id):
                    finish = False
                    return
                logger.info("execution.started run=%s", run_id)
                snapshot = row.config_snapshot
                plan = await asyncio.to_thread(self.prepare, row, messages)

                def authorize(active, db=None, invocation=None):
                    extra = {"invocation": invocation} if invocation is not None else {}
                    return self.authorize(row, active, db=db, **extra)

                hooks = RunControl(run_id, self.store, authorize)
                hooks.restore(await asyncio.to_thread(self.store.restore_control, run_id))
                execution = asyncio.create_task(plan.execute(hooks))
                watcher = asyncio.create_task(self._watch(row, hooks))
                done, _ = await asyncio.wait(
                    (execution, watcher), return_when=asyncio.FIRST_COMPLETED
                )
                # A persisted stop/storage error wins even if execution finishes simultaneously.
                if watcher in done:
                    await watcher
                result = await execution
                if not result.text.strip():
                    raise ExecutionFailure("empty_response")
                if len(result.text.encode()) > snapshot["max_output_bytes"]:
                    raise ExecutionFailure(
                        "output_limit_exceeded",
                        truncate(result.text, snapshot["max_output_bytes"])
                        if plan.publish_partial
                        else None,
                    )
                await hooks.guard()
                text, usage, structured = result.text, result.usage, result.structured_result
                status, code = "succeeded", None
        except asyncio.CancelledError:
            status, code = "interrupted", "runtime_interrupted"
            if resumable:
                finish = False
            raise
        except (SQLAlchemyError, sqlite3.Error, PublicationFailure):
            self.pending_failures.add(run_id)
            self.status.phase = "degraded"
            return
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
            if isinstance(error, ExecutionFailure) and (plan is None or plan.publish_partial):
                text = error.partial_text or ""
            if code == "execution_failed":
                logger.error("Execution failed run=%s type=%s", run_id, type(error).__name__)
        finally:
            for task in (execution, watcher):
                if task and not task.done():
                    task.cancel()
            await asyncio.gather(
                *(task for task in (execution, watcher) if task), return_exceptions=True
            )
            if not finish and hooks:
                try:
                    await asyncio.to_thread(
                        self.store.update_progress, run_id, hooks.progress.pending()
                    )
                except (SQLAlchemyError, sqlite3.Error, PublicationFailure):
                    pass
            if finish and run_id not in self.pending_failures:
                try:
                    await asyncio.to_thread(
                        self.publish,
                        Completion(
                            run_id=run_id,
                            content=text,
                            status=status,
                            error=None if code == "user_cancelled" else code,
                            usage=usage,
                            structured=structured,
                            progress=tuple(hooks.progress.pending() if hooks else ()),
                        ),
                    )
                except (SQLAlchemyError, sqlite3.Error, PublicationFailure):
                    self.pending_failures.add(run_id)
                    self.status.phase = "degraded"
