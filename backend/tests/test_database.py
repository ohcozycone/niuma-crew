"""Real file-based SQLite tests for persistence, isolation and transaction safety."""

import pytest
from sqlalchemy import URL, MetaData, Table, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.config import DatabaseConfig
from app.infrastructure.database.errors import is_database_busy
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer


@pytest.fixture
def database(tmp_path):
    database = Database(
        DatabaseConfig(
            url=URL.create("sqlite+pysqlite", database=str(tmp_path / "storage/test.db"))
        )
    )
    with database.engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE children (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parents(id))"
        )
    yield database
    database.close()


def test_committed_changes_survive_reopening(database):
    with database.transaction() as session:
        session.execute(text("INSERT INTO parents VALUES (1)"))
    database.close()
    reopened = Database(DatabaseConfig(url=database.engine.url))
    try:
        with reopened.transaction() as session:
            assert session.execute(text("SELECT id FROM parents")).scalars().all() == [1]
    finally:
        reopened.close()


def test_failed_transaction_rolls_back_and_releases_connection(database):
    with pytest.raises(RuntimeError, match="abort"):
        with database.transaction() as session:
            session.execute(text("INSERT INTO parents VALUES (1)"))
            raise RuntimeError("abort")
    with database.transaction() as session:
        assert session.execute(text("SELECT count(*) FROM parents")).scalar_one() == 0
        session.execute(text("INSERT INTO parents VALUES (2)"))


def test_foreign_keys_and_pragmas_apply_to_each_connection(database):
    with database.engine.connect() as first, database.engine.connect() as second:
        for connection in (first, second):
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000
            assert connection.exec_driver_sql("PRAGMA synchronous").scalar_one() == 2
    with pytest.raises(IntegrityError):
        with database.transaction() as session:
            session.execute(text("INSERT INTO parents VALUES (1)"))
            session.execute(text("INSERT INTO children VALUES (1, 999)"))
    with database.transaction() as session:
        assert session.execute(text("SELECT count(*) FROM parents")).scalar_one() == 0


def test_ddl_participates_in_rollback(database):
    with pytest.raises(RuntimeError, match="abort"):
        with database.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE unfinished (id INTEGER PRIMARY KEY)")
            raise RuntimeError("abort")
    assert "unfinished" not in inspect(database.engine).get_table_names()


def test_released_savepoint_still_rolls_back_with_outer_transaction(database):
    with pytest.raises(RuntimeError, match="abort"):
        with database.transaction() as session:
            with session.begin_nested():
                session.execute(text("INSERT INTO parents VALUES (1)"))
            raise RuntimeError("abort")
    with database.transaction() as session:
        assert session.execute(text("SELECT count(*) FROM parents")).scalar_one() == 0


def test_wal_reader_keeps_snapshot_while_another_connection_commits(database):
    with database.transaction() as reader:
        assert reader.execute(text("SELECT count(*) FROM parents")).scalar_one() == 0
        with database.transaction() as writer:
            writer.execute(text("INSERT INTO parents VALUES (1)"))
        assert reader.execute(text("SELECT count(*) FROM parents")).scalar_one() == 0
    with database.transaction() as reader:
        assert reader.execute(text("SELECT count(*) FROM parents")).scalar_one() == 1


def test_contending_writer_times_out_then_recovers_after_lock_release(database):
    other = Database(DatabaseConfig(url=database.engine.url, busy_timeout_ms=20))
    try:
        # Open the other connection before acquiring the write lock.
        with other.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 20
        with database.transaction() as first:
            first.execute(text("INSERT INTO parents VALUES (1)"))
            with pytest.raises(OperationalError, match="locked") as caught:
                with other.transaction() as second:
                    second.execute(text("INSERT INTO parents VALUES (2)"))
            assert is_database_busy(caught.value)
        with other.transaction() as second:
            second.execute(text("INSERT INTO parents VALUES (2)"))
        with database.transaction() as session:
            assert session.execute(text("SELECT count(*) FROM parents")).scalar_one() == 2
    finally:
        other.close()


def test_write_reservation_blocks_writers_without_changing_rows_or_blocking_readers(database):
    # This schema has no conversations or other application tables.
    parents = Table("parents", MetaData(), autoload_with=database.engine)
    other = Database(DatabaseConfig(url=database.engine.url, busy_timeout_ms=20))
    try:
        with other.engine.connect():
            pass
        with database.transaction() as first:
            reserve_writer(first, parents)
            assert first.execute(text("SELECT count(*) FROM parents")).scalar_one() == 0
            with other.transaction() as reader:
                assert reader.execute(text("SELECT count(*) FROM parents")).scalar_one() == 0
            with pytest.raises(OperationalError, match="locked"):
                with other.transaction() as writer:
                    writer.execute(text("INSERT INTO parents VALUES (1)"))
        with other.transaction() as writer:
            writer.execute(text("INSERT INTO parents VALUES (2)"))
    finally:
        other.close()


def test_reserved_write_remains_in_the_callers_rollback_boundary(database):
    parents = Table("parents", MetaData(), autoload_with=database.engine)
    with pytest.raises(RuntimeError, match="abort"):
        with database.transaction() as session:
            reserve_writer(session, parents)
            session.execute(text("INSERT INTO parents VALUES (1)"))
            raise RuntimeError("abort")
    with database.transaction() as session:
        assert session.execute(text("SELECT count(*) FROM parents")).scalar_one() == 0
