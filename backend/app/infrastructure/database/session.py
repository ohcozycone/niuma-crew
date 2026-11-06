"""SQLite connections and short, explicit units of work."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from sqlite3 import Connection

from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class DatabaseConfig:
    """数据库连接配置；当前仅支持文件型 SQLite。"""

    url: URL = field(repr=False)  # 解析后的绝对文件 URL，不在 repr 中暴露连接信息。
    busy_timeout_ms: int = 5000  # 写锁冲突等待时限，毫秒；0 表示立即失败。

    def __post_init__(self) -> None:
        if not 0 <= self.busy_timeout_ms <= 2_147_483_647:
            raise ValueError("SQLITE_BUSY_TIMEOUT_MS 必须是 0 到 2147483647 之间的整数。")


class Database:
    def __init__(self, config: DatabaseConfig) -> None:
        Path(config.url.database).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            config.url,
            hide_parameters=True,
            connect_args={
                "autocommit": False,
                "check_same_thread": False,
                "timeout": config.busy_timeout_ms / 1000,
            },
        )
        event.listen(self.engine, "connect", self._configure_connection)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def _configure_connection(connection: Connection, _record: object) -> None:
        # These PRAGMAs must run outside a transaction, before the connection is used.
        connection.autocommit = True
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            mode = cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode.lower() != "wal":
                raise RuntimeError("无法为 SQLite 数据库启用 WAL 模式。")
            cursor.execute("PRAGMA synchronous=FULL")
        finally:
            cursor.close()
            connection.autocommit = False

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """Commit on success, roll back on failure, and always release the session.

        Model/tool calls belong outside this scope. A Session must not be shared
        between concurrent requests or tasks.
        """
        with self._sessions.begin() as session:
            yield session

    def close(self) -> None:
        self.engine.dispose()
