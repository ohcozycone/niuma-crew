"""Use the same SQLite settings and transaction behavior as the application."""

from logging.config import fileConfig

from alembic import context

from app.config import load_config
from app.infrastructure.database.models import Base
from app.infrastructure.database.session import Database

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The model registry loads every table before Alembic compares metadata.
target_metadata = Base.metadata
settings = load_config().database


def include_name(name, type_, parent_names):
    # FTS5 and its SQLite-owned shadow tables are managed explicitly in 0013,
    # never reflected as ordinary ORM tables or proposed for removal.
    fts_tables = {"knowledge_fts"} | {
        "knowledge_fts_" + suffix for suffix in ("data", "idx", "content", "docsize", "config")
    }
    return type_ != "table" or name not in fts_tables


def run_migrations_offline() -> None:
    context.configure(
        url=settings.url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        transactional_ddl=True,
        compare_server_default=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    database = Database(settings)
    try:
        with database.engine.connect() as connection:
            # SQLite cannot rebuild a referenced users table with FK enforcement on:
            # DROP TABLE would cascade-delete sessions. Disable it only on this migration
            # connection, then validate every FK before committing the atomic migration.
            raw = connection.connection.driver_connection
            raw.autocommit = True
            raw.execute("PRAGMA foreign_keys=OFF")
            raw.autocommit = False
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                transactional_ddl=True,
                compare_server_default=True,
                include_name=include_name,
            )
            with context.begin_transaction():
                context.run_migrations()
                if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                    raise RuntimeError("迁移后的外键检查失败，已回滚。")
            raw.autocommit = True
            raw.execute("PRAGMA foreign_keys=ON")
            raw.autocommit = False
    finally:
        database.close()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
