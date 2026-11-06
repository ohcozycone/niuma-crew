"""Lifespan-owned, single-file scanner for durable keyword jobs."""

import asyncio
import fcntl
import logging
import os
from pathlib import Path
from typing import IO

from sqlalchemy.exc import SQLAlchemyError

from app.knowledge.processing import KnowledgeProcessingService

logger = logging.getLogger(__name__)


class KnowledgeWorker:
    def __init__(self, processing: KnowledgeProcessingService, lock_path: Path):
        self.processing, self.lock_path = processing, lock_path
        self.task: asyncio.Task[None] | None = None
        self.lock: IO[str] | None = None
        self.stopping = False

    async def start(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.lock_path.open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.chmod(lock.name, 0o600)
            await asyncio.to_thread(self.processing.knowledge.vectors.reconcile)
            await asyncio.to_thread(self.processing.recover)
        except BaseException:
            lock.close()
            raise
        self.lock = lock
        self.task = asyncio.create_task(self.loop())

    async def stop(self) -> None:
        self.stopping = True
        try:
            if self.task:
                # Cancelling to_thread does not stop its writer; join before closing the DB/lock.
                await self.task
        finally:
            self.task = None
            if self.lock:
                self.lock.close()
                self.lock = None

    async def loop(self) -> None:
        needs_recovery = False
        while not self.stopping:
            try:
                if needs_recovery:
                    await asyncio.to_thread(self.processing.recover)
                    needs_recovery = False
                worked = await asyncio.to_thread(self.processing.run_next)
            except SQLAlchemyError:
                logger.warning("Knowledge worker database unavailable; durable jobs retained")
                needs_recovery = True
                worked = False
            if not worked:
                await asyncio.sleep(0.5)
