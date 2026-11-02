"""Configuration sources remain local and preserve environment precedence."""

import os
from pathlib import Path

import pytest

from app.config import load_config
from app.execution.config import RuntimeConfig, load_runtime_config


@pytest.fixture(autouse=True)
def isolated_storage_environment(monkeypatch):
    for name in (
        "APP_DATA_DIR",
        "DATABASE_URL",
        "SQLITE_BUSY_TIMEOUT_MS",
        "MODEL_CONNECTIONS_KEY_FILE",
        "RUNNER_LOCK_FILE",
        "RUN_RECURSION_LIMIT",
        "RUN_MAX_MODEL_CALLS",
        "RUN_MAX_SKILL_READS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_configuration_paths_stay_under_backend_project(monkeypatch):
    dotenv_paths = []

    def dotenv_values(path):
        dotenv_paths.append(path)
        return {}

    monkeypatch.setattr("app.config.dotenv_values", dotenv_values)
    backend_dir = Path(__file__).resolve().parents[1]
    config = load_config()
    assert dotenv_paths == [backend_dir / ".env"]
    assert Path(config.database.url.database) == backend_dir / ".data/app.db"
    assert config.model_encryption_key_file == backend_dir / ".data/model-connections.key"
    assert config.runner_lock_file == backend_dir / ".data/runner.lock"
    assert config.runtime.recursion_limit == 64
    assert config.runtime.max_model_calls == 8
    assert config.runtime.max_skill_reads == 16


def test_dotenv_values_do_not_leak_between_configurations(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "DATABASE_URL=sqlite+pysqlite:///file.db\nSQLITE_BUSY_TIMEOUT_MS=1200\n"
    )
    config = load_config(tmp_path)
    assert Path(config.database.url.database) == tmp_path / ".data/file.db"
    assert config.database.busy_timeout_ms == 1200
    assert "DATABASE_URL" not in os.environ

    other = tmp_path / "other"
    other.mkdir()
    other_config = load_config(other)
    assert Path(other_config.database.url.database) == other / ".data/app.db"
    assert other_config.database.busy_timeout_ms == 5000


def test_environment_overrides_dotenv_including_empty_values(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("APP_DATA_DIR=storage\nSQLITE_BUSY_TIMEOUT_MS=1200\n")
    monkeypatch.setenv("APP_DATA_DIR", " env-storage ")
    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "2500")
    config = load_config(tmp_path)
    assert Path(config.database.url.database) == tmp_path / "env-storage/app.db"
    assert config.database.busy_timeout_ms == 2500
    monkeypatch.setenv("APP_DATA_DIR", " ")
    with pytest.raises(ValueError, match="APP_DATA_DIR"):
        load_config(tmp_path)


def test_database_configuration_does_not_create_storage(tmp_path):
    config = load_config(tmp_path)
    assert Path(config.database.url.database) == tmp_path / ".data/app.db"
    assert config.model_encryption_key_file == tmp_path / ".data/model-connections.key"
    assert config.runner_lock_file == tmp_path / ".data/runner.lock"
    assert config.database.busy_timeout_ms == 5000
    assert not (tmp_path / ".data").exists()
    assert str(config.database.url) not in repr(config)


def test_database_paths_and_environment_precedence(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "APP_DATA_DIR=storage\nDATABASE_URL=sqlite+pysqlite:///data/file.db\n"
        "MODEL_CONNECTIONS_KEY_FILE=secrets/models.key\nRUNNER_LOCK_FILE=runtime/runner.lock\n"
        "SQLITE_BUSY_TIMEOUT_MS=1200\n"
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    config = load_config(tmp_path)
    assert Path(config.database.url.database) == tmp_path / "storage/data/file.db"
    assert config.model_encryption_key_file == tmp_path / "storage/secrets/models.key"
    assert config.runner_lock_file == tmp_path / "storage/runtime/runner.lock"
    assert config.database.busy_timeout_ms == 1200
    assert "DATABASE_URL" not in os.environ
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{elsewhere / 'env.db'}")
    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "2500")
    changed = load_config(tmp_path)
    assert Path(changed.database.url.database) == elsewhere / "env.db"
    assert changed.database.busy_timeout_ms == 2500
    assert changed.model_encryption_key_file == config.model_encryption_key_file
    assert changed.runner_lock_file == config.runner_lock_file


def test_absolute_storage_paths_are_independent_of_data_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "volume"))
    monkeypatch.setenv("MODEL_CONNECTIONS_KEY_FILE", str(tmp_path / "secrets/key"))
    monkeypatch.setenv("RUNNER_LOCK_FILE", str(tmp_path / "runtime/lock"))
    config = load_config(tmp_path)
    assert Path(config.database.url.database) == tmp_path / "volume/app.db"
    assert config.model_encryption_key_file == tmp_path / "secrets/key"
    assert config.runner_lock_file == tmp_path / "runtime/lock"
    assert not (tmp_path / "volume").exists()


@pytest.mark.parametrize(
    "name", ["APP_DATA_DIR", "DATABASE_URL", "MODEL_CONNECTIONS_KEY_FILE", "RUNNER_LOCK_FILE"]
)
@pytest.mark.parametrize("value", ["", " "])
def test_empty_storage_environment_does_not_fall_back_to_dotenv(tmp_path, monkeypatch, name, value):
    (tmp_path / ".env").write_text(f"{name}=sqlite+pysqlite:///file.db\n")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        load_config(tmp_path)


@pytest.mark.parametrize(
    "value",
    [
        "invalid-secret",
        "postgresql+psycopg://user:private-secret@host/db",
        "sqlite+pysqlite://",
        "sqlite+pysqlite:///:memory:",
        "sqlite+pysqlite:///file:memory?mode=memory&uri=true",
        "sqlite+pysqlite:///test.db?timeout=0",
        "sqlite+pysqlite://user:private-secret@host/test.db",
        "sqlite+pysqlite://host:private-secret/test.db",
    ],
)
def test_unsupported_database_urls_fail_without_exposing_url(tmp_path, monkeypatch, value):
    monkeypatch.setenv("DATABASE_URL", value)
    with pytest.raises(ValueError, match="DATABASE_URL") as error:
        load_config(tmp_path)
    assert value not in str(error.value)
    assert "private-secret" not in str(error.value)
    assert not (tmp_path / ".data").exists()


@pytest.mark.parametrize("value", ["", "invalid", "-1", "2147483648"])
def test_invalid_database_timeout_fails_clearly(tmp_path, monkeypatch, value):
    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", value)
    with pytest.raises(ValueError, match="SQLITE_BUSY_TIMEOUT_MS"):
        load_config(tmp_path)


def test_runtime_budgets_load_through_app_config_with_environment_precedence(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "RUN_RECURSION_LIMIT=96\nRUN_MAX_MODEL_CALLS=12\nRUN_MAX_SKILL_READS=24\n"
    )
    monkeypatch.setenv("RUN_MAX_MODEL_CALLS", "3")
    config = load_config(tmp_path)
    assert config.runtime.recursion_limit == 96
    assert config.runtime.max_model_calls == 3
    assert config.runtime.max_skill_reads == 24
    assert "RUN_RECURSION_LIMIT" not in os.environ
    monkeypatch.setenv("RUN_RECURSION_LIMIT", "")
    with pytest.raises(ValueError, match="RUN_RECURSION_LIMIT"):
        load_config(tmp_path)


@pytest.mark.parametrize("name", ["RECURSION_LIMIT", "MAX_MODEL_CALLS", "MAX_SKILL_READS"])
@pytest.mark.parametrize("value", ["0", "-1", "1.5", "nan", "inf", "", None])
def test_runtime_budgets_reject_invalid_environment_values(name, value):
    with pytest.raises(ValueError, match=f"RUN_{name}"):
        load_runtime_config({f"RUN_{name}": value})


@pytest.mark.parametrize("name", ["recursion_limit", "max_model_calls", "max_skill_reads"])
@pytest.mark.parametrize("value", [1.5, True])
def test_runtime_budgets_require_integers_when_injected(name, value):
    with pytest.raises(ValueError, match=f"RUN_{name.upper()}.*正整数"):
        RuntimeConfig(**{name: value})
