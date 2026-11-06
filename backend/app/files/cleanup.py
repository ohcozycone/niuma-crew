"""Clean unheld metadata and bytes using injected owner queries."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from sqlalchemy import or_, select

from app.files.models import StoredFile
from app.infrastructure.database.transactions import reserve_writer
from app.values import utc_now


class FileCleanup:
    def __init__(self, database, storage, config):
        self.database, self.storage, self.config = (database, storage, config)
        self.directory = storage.directory
        self.cleanup_after = None
        self.maintenance_task = None
        self.stop_event = None

    def sweep(self, retained):
        cutoff = utc_now() - timedelta(seconds=self.config.retention_seconds)
        removed = []
        with self.database.transaction() as db:
            reserve_writer(db, StoredFile.__table__)
            query = select(StoredFile).where(StoredFile.created_at < cutoff)
            if self.cleanup_after:
                created_at, id = self.cleanup_after
                query = query.where(
                    or_(
                        StoredFile.created_at > created_at,
                        (StoredFile.created_at == created_at) & (StoredFile.id > id),
                    )
                )
            candidates = list(
                db.scalars(query.order_by(StoredFile.created_at, StoredFile.id).limit(128))
            )
            self.cleanup_after = (
                (candidates[-1].created_at, candidates[-1].id) if len(candidates) == 128 else None
            )
            keep = retained(db, candidates)
            for row in candidates:
                if row.id not in keep:
                    removed.append(row.storage_key)
                    db.delete(row)
        for key in removed:
            (self.directory / key).unlink(missing_ok=True)
        if self.directory.exists():
            with self.database.transaction() as db:
                known = set(db.scalars(select(StoredFile.storage_key)))
            for path in self.directory.iterdir():
                if (
                    path.name not in known
                    and path.is_file()
                    and (not path.is_symlink())
                    and (path.stat().st_mtime < time.time() - self.config.retention_seconds)
                ):
                    path.unlink(missing_ok=True)

    async def start(self, retained):
        self.stop_event = asyncio.Event()

        async def maintain():
            while not self.stop_event.is_set():
                try:
                    await asyncio.to_thread(self.sweep, retained)
                except Exception:
                    logging.getLogger(__name__).warning("files.maintenance_failed")
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=60)
                except TimeoutError:
                    pass

        self.maintenance_task = asyncio.create_task(maintain())

    async def stop(self):
        if self.stop_event is not None:
            self.stop_event.set()
        if self.maintenance_task is not None:
            await self.maintenance_task
