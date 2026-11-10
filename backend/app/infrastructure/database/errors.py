import sqlite3

from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError


def _sqlite_code(error: DBAPIError) -> int | None:
    if not isinstance(error.orig, sqlite3.Error):
        return None
    return getattr(error.orig, "sqlite_errorcode", None)


def is_unique_violation(error: IntegrityError, *, table: str, columns: tuple[str, ...]) -> bool:
    if not columns or _sqlite_code(error) != sqlite3.SQLITE_CONSTRAINT_UNIQUE:
        return False
    # SQLite 唯一冲突报告列名，不报告约束或索引名。
    expected = ", ".join(f"{table}.{column}" for column in columns)
    return str(error.orig) == f"UNIQUE constraint failed: {expected}"


def is_database_busy(error: OperationalError) -> bool:
    code = _sqlite_code(error)
    return code is not None and code & 0xFF in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
