from sqlalchemy import Table, false, update
from sqlalchemy.orm import Session
from sqlalchemy.sql import FromClause


def reserve_writer(session: Session, table: FromClause) -> None:
    """业务读取前用空 UPDATE 取得写锁，空表同样有效且不改行。

    调用方须提供带主键的现存表，并保持同一事务；读后加锁不能修复已过期的 WAL 快照。"""
    if not isinstance(table, Table):
        raise TypeError("写入预留需要真实业务表。")
    key = next(iter(table.primary_key.columns))
    session.execute(update(table).where(false()).values({key: key}))
