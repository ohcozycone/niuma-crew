"""Idempotently adopt completed execution results in a separate business transaction."""

import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select

from app.conversations.models import Conversation, ConversationRun, MessageFile
from app.conversations.writes import publish_conversation
from app.errors import RateLimitError, ServiceError, ServiceUnavailableError
from app.execution.errors import ExecutionFailure
from app.execution.models import TERMINAL, Run
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.values import utc_now

logger = logging.getLogger(__name__)


class ConversationAcceptance:
    """Own business association, retries and rejection; never write a Run terminal state."""

    def __init__(self, database: Database, authorize: Any, interval: float = 0.25) -> None:
        self.database, self.authorize, self.interval = database, authorize, interval
        self.publish_content = publish_conversation
        self.task: asyncio.Task | None = None
        self._wake = asyncio.Event()

    def process(self, run_id: str) -> None:
        try:
            with self.database.transaction() as db:
                reserve_writer(db, ConversationRun.__table__)
                binding = db.get(ConversationRun, run_id)
                row = db.get(Run, run_id)
                if (
                    binding is None
                    or binding.handled_at is not None
                    or row is None
                    or row.status not in TERMINAL
                ):
                    return
                content = row.result_text
                if row.status == "succeeded":
                    self.authorize(row, db=db)
                    for ref in (row.result_data or {}).get("output_files", []):
                        db.merge(MessageFile(message_id=binding.run_id, file_id=ref["id"]))
                self.publish_content(db, row, content)
                binding.handled_at = utc_now()
                binding.acceptance_error = None
                binding.next_acceptance_at = None
                binding.acceptance_attempts += 1
        except Exception as error:
            # The execution result has already committed. Record retry/rejection in
            # a fresh business transaction, never mark the successful Run failed.
            with self.database.transaction() as db:
                reserve_writer(db, ConversationRun.__table__)
                binding = db.get(ConversationRun, run_id)
                if binding is None or binding.handled_at is not None:
                    return
                binding.acceptance_attempts += 1
                binding.acceptance_error = (
                    error.code
                    if isinstance(error, (ServiceError, ExecutionFailure))
                    else "acceptance_unavailable"
                )
                if isinstance(error, (ServiceError, ExecutionFailure)) and not isinstance(
                    error, (ServiceUnavailableError, RateLimitError)
                ):
                    binding.handled_at, binding.active = utc_now(), False
                    binding.next_acceptance_at = None
                    conversation = db.get(Conversation, binding.conversation_id)
                    if conversation is not None:
                        conversation.revision += 1
                        conversation.updated_at = utc_now()
                else:
                    binding.next_acceptance_at = utc_now() + timedelta(
                        seconds=min(60, 2 ** min(binding.acceptance_attempts, 6))
                    )
            logger.warning(
                "conversation.acceptance_failed run=%s type=%s", run_id, type(error).__name__
            )

    def sweep(self) -> None:
        with self.database.transaction() as db:
            ids = list(
                db.scalars(
                    select(ConversationRun.run_id)
                    .join(Run, Run.id == ConversationRun.run_id)
                    .where(
                        Run.status.in_(TERMINAL),
                        ConversationRun.handled_at.is_(None),
                        or_(
                            ConversationRun.next_acceptance_at.is_(None),
                            ConversationRun.next_acceptance_at <= utc_now(),
                        ),
                    )
                    .order_by(Run.finished_at, Run.id)
                    .limit(64)
                )
            )
        for id in ids:
            self.process(id)

    def wake(self) -> None:
        """Hint that committed work may be ready; the database remains authoritative."""
        self._wake.set()

    async def _loop(self) -> None:
        while True:
            self._wake.clear()
            scan = asyncio.create_task(asyncio.to_thread(self.sweep))
            try:
                await asyncio.shield(scan)
            except asyncio.CancelledError:
                # A cancelled to_thread await does not stop its database transaction.
                # Join that work before lifespan closes resource services and the DB.
                await asyncio.gather(scan, return_exceptions=True)
                raise
            except Exception as error:
                logger.warning("conversation.acceptance_scan_failed type=%s", type(error).__name__)
            try:
                await asyncio.wait_for(self._wake.wait(), self.interval)
            except TimeoutError:
                pass

    async def start(self) -> None:
        self.task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
