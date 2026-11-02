"""Recognize actual SQLite failures without confusing unrelated constraints."""

import sqlite3

import pytest
from sqlalchemy import URL, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.config import DatabaseConfig
from app.infrastructure.database.errors import is_database_busy, is_unique_violation
from app.infrastructure.database.session import Database


@pytest.fixture
def database(tmp_path):
    database = Database(
        DatabaseConfig(url=URL.create("sqlite+pysqlite", database=str(tmp_path / "errors.db")))
    )
    with database.engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO parents VALUES (1)")
        connection.exec_driver_sql(
            "CREATE TABLE records (id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE, "
            "revision INTEGER CHECK (revision > 0), parent_id INTEGER REFERENCES parents(id))"
        )
        connection.exec_driver_sql("INSERT INTO records VALUES (1, 'original', 1, 1)")
        connection.exec_driver_sql(
            "CREATE TABLE pairs (left_value TEXT, right_value TEXT, UNIQUE(left_value, right_value))"
        )
        connection.exec_driver_sql("INSERT INTO pairs VALUES ('left', 'right')")
    yield database
    database.close()


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("INSERT INTO records VALUES (2, 'original', 1, 1)", True),
        ("INSERT INTO records VALUES (1, 'different', 1, 1)", False),
        ("INSERT INTO records VALUES (2, NULL, 1, 1)", False),
        ("INSERT INTO records VALUES (2, 'different', 0, 1)", False),
        ("INSERT INTO records VALUES (2, 'different', 1, 999)", False),
    ],
)
def test_unique_recognition_requires_the_exact_constraint(database, statement, expected):
    with pytest.raises(IntegrityError) as caught:
        with database.transaction() as session:
            session.execute(text(statement))
    error = caught.value
    assert is_unique_violation(error, table="records", columns=("label",)) is expected
    assert not is_unique_violation(error, table="other_records", columns=("label",))
    assert not is_unique_violation(error, table="records", columns=("other_label",))


def test_composite_unique_requires_all_columns(database):
    with pytest.raises(IntegrityError) as caught:
        with database.transaction() as session:
            session.execute(text("INSERT INTO pairs VALUES ('left', 'right')"))
    assert is_unique_violation(caught.value, table="pairs", columns=("left_value", "right_value"))
    assert not is_unique_violation(caught.value, table="pairs", columns=("left_value",))
    assert not is_unique_violation(caught.value, table="pairs", columns=())


def test_unknown_driver_or_missing_sqlite_code_is_not_recognized():
    foreign_driver = Exception("UNIQUE constraint failed: records.label")
    foreign_driver.sqlite_errorcode = sqlite3.SQLITE_CONSTRAINT_UNIQUE
    for original in (foreign_driver, sqlite3.IntegrityError(str(foreign_driver))):
        assert not is_unique_violation(
            IntegrityError("", None, original), table="records", columns=("label",)
        )
    foreign_busy = Exception("database is locked")
    foreign_busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
    for original in (foreign_busy, sqlite3.OperationalError("database is locked")):
        assert not is_database_busy(OperationalError("", None, original))


def test_extended_busy_snapshot_is_recognized(database):
    with pytest.raises(OperationalError) as caught:
        with database.transaction() as reader:
            reader.execute(text("SELECT * FROM records")).all()
            with database.transaction() as writer:
                writer.execute(text("INSERT INTO records VALUES (2, 'writer', 1, 1)"))
            reader.execute(text("INSERT INTO records VALUES (3, 'stale-reader', 1, 1)"))
    assert caught.value.orig.sqlite_errorcode == sqlite3.SQLITE_BUSY_SNAPSHOT
    assert is_database_busy(caught.value)


def test_locked_table_is_recognized(database):
    with database.engine.connect() as connection:
        result = connection.exec_driver_sql("SELECT * FROM pairs")
        try:
            with pytest.raises(OperationalError) as caught:
                connection.exec_driver_sql("DROP TABLE pairs")
            assert caught.value.orig.sqlite_errorcode == sqlite3.SQLITE_LOCKED
            assert is_database_busy(caught.value)
        finally:
            result.close()


def test_other_operational_errors_are_not_busy(database):
    with pytest.raises(OperationalError) as caught:
        with database.transaction() as session:
            session.execute(text("SELECT * FROM missing_table"))
    assert not is_database_busy(caught.value)
