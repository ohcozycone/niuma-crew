"""Offline fixtures with isolated application storage per test."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from scenario_client import ScenarioClient as TestClient
from sqlalchemy import URL

from app.auth.service import AuthService
from app.bootstrap import create_app
from app.config import AppConfig, DatabaseConfig
from app.execution.config import RuntimeConfig
from app.infrastructure.database.session import Database
from app.skills.config import SkillConfig


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        database=DatabaseConfig(
            url=URL.create("sqlite+pysqlite", database=str(tmp_path / "app.db"))
        ),
        model_encryption_key_file=tmp_path / "secrets/model-connections.key",
        runner_lock_file=tmp_path / "runtime/runner.lock",
        runtime=RuntimeConfig(enabled=False),
        skills=SkillConfig(library_directory=tmp_path / ".agents" / "skills"),
    )


@pytest.fixture
def client(app_config):
    with TestClient(create_app(app_config)) as client:
        yield client


@pytest.fixture
def migrated_config(app_config, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", app_config.database.url.render_as_string(hide_password=False)
    )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    return app_config


@pytest.fixture
def api_client(migrated_config):
    database = Database(migrated_config.database)
    try:
        AuthService(database, migrated_config.auth).initialize_admin("admin", "test-password-auth")
    finally:
        database.close()
    with TestClient(
        create_app(migrated_config),
        headers={"Origin": "http://localhost:3000", "Content-Type": "application/json"},
    ) as client:
        assert (
            client.post(
                "/api/auth/login", json={"username": "admin", "password": "test-password-auth"}
            ).status_code
            == 200
        )
        yield client
