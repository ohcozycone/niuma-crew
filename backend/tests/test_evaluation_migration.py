from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.auth.service import AuthService
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
    agent_id, run_id = str(uuid4()), 100000000001
    # 按0021的冻结字段写入，不能让当前应用服务读写历史结构。
    with db.transaction() as session:
        user_id = session.scalar(text("SELECT id FROM users WHERE username='admin'"))
        session.execute(
            text("INSERT INTO agents (id,name,avatar_id) VALUES (:id,'旧员工','admin')"),
            {"id": agent_id},
        )
        session.execute(
            text(
                'INSERT INTO runs (id,agent_id,owner_user_id,initiated_by_user_id,origin_kind,operation,"trigger",mode,client_request_id,request_hash,config_snapshot,input_snapshot,thread_id,result_text,status,finished_at) '
                "VALUES (:id,:agent,:user,:user,'test','test.accept','user','interactive','fixture','fixture','{}','[]','migration-fixture',:result,'succeeded',:finished)"
            ),
            {
                "id": run_id,
                "agent": agent_id,
                "user": user_id,
                "result": "升级前的正式成果",
                "finished": utc_now().isoformat(),
            },
        )
    db.close()
    command.upgrade(config, "0022")
    db = Database(app_config.database)
    try:
        with db.transaction() as session:
            row = session.execute(
                text("SELECT result_text,status FROM runs WHERE id=:id"), {"id": run_id}
            ).one()
            assert row == ("升级前的正式成果", "succeeded")
            assert session.execute(text("PRAGMA foreign_key_check")).all() == []
            assert session.scalar(text("SELECT count(*) FROM evaluation_batches")) == 0
    finally:
        db.close()
