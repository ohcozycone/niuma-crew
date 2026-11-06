"""Persist SDK checkpoints independently of product history and run resources."""

import sqlite3
from contextlib import asynccontextmanager, closing, contextmanager
from pathlib import Path
from threading import Lock
from typing import NotRequired

from deepagents.middleware.filesystem import FilesystemState
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.execution.contracts import RuntimeFailure
from app.execution.runtime.concurrency import run_sync


class AgentRunState(FilesystemState):
    app_run_id: NotRequired[str]
    completed_run_id: NotRequired[str]
    model_usage: NotRequired[dict[str, int | None]]
    memory_scope: NotRequired[str]


def checkpoint_config(run_thread_id: str, checkpoint_id: str | None = None, run_id="") -> dict:
    config = {
        "configurable": {"thread_id": run_thread_id, "checkpoint_ns": ""},
        "metadata": {"app_run_id": run_id},
    }
    if checkpoint_id:
        config["configurable"]["checkpoint_id"] = checkpoint_id
    return config


class TrackingSqliteSaver(AsyncSqliteSaver):
    on_saved = None

    async def aput(self, config, checkpoint, metadata, new_versions):
        result = await super().aput(config, checkpoint, metadata, new_versions)
        run_id = config.get("metadata", {}).get("app_run_id")
        if run_id and self.on_saved:
            # SDK 提交与业务引用不是一个事务；恢复时还会按 metadata 核对最新存档。
            await self.on_saved(checkpoint["id"])
        return result


class CheckpointStore:
    def __init__(self, database_path: str):
        self.path = Path(database_path).with_suffix(".checkpoints.db")
        self._setup_lock = Lock()

    @contextmanager
    def reader(self):
        with closing(sqlite3.connect(str(self.path), timeout=5, check_same_thread=False)) as conn:
            saver = SqliteSaver(conn)
            with self._setup_lock:
                saver.setup()
            yield saver

    def _prepare(self):
        with self.reader():
            pass

    @asynccontextmanager
    async def writer(self, on_saved):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Fresh saver connections can race while switching SQLite to WAL.
            # Initialize under the same gate as readers, off the event loop;
            # execution and checkpoint writes remain concurrent after setup.
            await run_sync(self._prepare)
            async with TrackingSqliteSaver.from_conn_string(str(self.path)) as saver:
                await saver.setup()
                saver.on_saved = on_saved
                yield saver
        except sqlite3.DatabaseError as error:
            raise RuntimeFailure("checkpoint_unavailable") from error

    def for_run(self, run_id: str, checkpoint_id: str | None, *, thread_id: str) -> str | None:
        if not self.path.exists():
            if checkpoint_id:
                raise RuntimeFailure("checkpoint_unavailable")
            return None
        try:
            with self.reader() as saver:
                latest = next(
                    saver.list(
                        checkpoint_config(thread_id),
                        filter={"app_run_id": run_id},
                        limit=1,
                    ),
                    None,
                )
            if latest:
                return latest.config["configurable"]["checkpoint_id"]
            if checkpoint_id:
                raise RuntimeFailure("checkpoint_unavailable")
            return None
        except sqlite3.DatabaseError as error:
            raise RuntimeFailure("checkpoint_unavailable") from error
