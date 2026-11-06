"""The assessment increment preserves pre-existing independent results."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from test_independent_runs import accept_work
from test_response_contract import employee

from app.auth.service import AuthService
from app.bootstrap import create_app
from app.execution.models import Run
from app.infrastructure.database.session import Database
from app.values import utc_now


def test_0022_adds_assessments_without_rebuilding_existing_records(app_config, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", app_config.database.url.render_as_string(hide_password=False)
    )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0021")
    db = Database(app_config.database)
    AuthService(db, app_config.auth).initialize_admin("admin", "test-password-auth")
    db.close()
    with TestClient(
        create_app(app_config),
        headers={
            "Origin": "http://localhost:3000",
            "Content-Type": "application/json",
        },
    ) as client:
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "username": "admin",
                    "password": "test-password-auth",
                },
            ).status_code
            == 200
        )
        agent = employee(client)
        run_id = accept_work(client, agent)
        # Arrange the frozen 0021 result directly. Current runtime queries require
        # the current schema and must not be exercised against historical columns.
        with client.app.state.database.transaction() as session:
            row = session.get(Run, run_id)
            row.result_text, row.status, row.finished_at = (
                "升级前的正式成果",
                "succeeded",
                utc_now(),
            )
    command.upgrade(config, "head")
    db = Database(app_config.database)
    try:
        with db.transaction() as session:
            row = session.scalar(select(Run).where(Run.id == run_id))
            assert row.result_text == "升级前的正式成果" and row.status == "succeeded"
            assert session.execute(text("PRAGMA foreign_key_check")).all() == []
            assert session.scalar(text("SELECT count(*) FROM evaluation_batches")) == 0
    finally:
        db.close()
