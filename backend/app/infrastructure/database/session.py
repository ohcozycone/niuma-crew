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

    url: URL = field(repr=False)  # 绝对文件 URL，不进入 repr。
    busy_timeout_ms: int = 5000  # 写锁等待毫秒数；0 表示立即失败。

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
        # 连接使用前在事务外设置这些 PRAGMA。
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
        """成功提交，异常回滚并释放会话；模型、工具调用放在事务外，会话不得并发共享。"""
        with self._sessions.begin() as session:
            yield session

    def close(self) -> None:
        self.engine.dispose()
