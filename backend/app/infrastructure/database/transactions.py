"""SQLite write reservation without depending on a particular business table."""

from sqlalchemy import Table, false, update
from sqlalchemy.orm import Session
from sqlalchemy.sql import FromClause


def reserve_writer(session: Session, table: FromClause) -> None:
    """Acquire SQLite's writer before business reads; retain the caller's transaction.

    An empty UPDATE acquires the write lock without modifying rows, including on
    an empty table. The caller supplies an existing table with a primary key.
    Calling this after a read cannot repair an already stale WAL snapshot.
    """
    if not isinstance(table, Table):
        raise TypeError("写入预留需要真实业务表。")
    key = next(iter(table.primary_key.columns))
    session.execute(update(table).where(false()).values({key: key}))
