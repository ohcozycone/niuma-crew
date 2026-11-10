"""使用旧库SQL构造0027升级输入，不调用已退役的个人API或ORM模型。"""

import sqlite3
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config


def test_0027_removes_forced_strategy_preserving_libraries(app_config, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", app_config.database.url.render_as_string(hide_password=False)
    )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0026")
    path = app_config.database.url.database
    user, kb = str(uuid4()), str(uuid4())
    cases = []
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO users(id,username,password_hash,role,is_active) VALUES (?,?,'historical-test-hash','admin',1)",
            (user, "historical-admin"),
        )
        db.execute(
            "INSERT INTO knowledge_bases(id,owner_user_id,client_request_id,name,description) VALUES (?,?,?,?,'')",
            (kb, user, str(uuid4()), "历史资料"),
        )
        for index, strategy in enumerate(("auto", "bm25", "vector", "hybrid")):
            employee, setting = str(uuid4()), str(uuid4())
            mode, top_k = ("always" if index % 2 else "on_demand"), index + 3
            db.execute(
                "INSERT INTO agents(id,name,avatar_id) VALUES (?,?,?)",
                (employee, "历史员工" + str(index), "default"),
            )
            db.execute(
                "INSERT INTO knowledge_employee_settings(id,user_id,agent_id,revision,mode,top_k,strategy) VALUES (?,?,?,7,?,?,?)",
                (setting, user, employee, mode, top_k, strategy),
            )
            db.execute(
                "INSERT INTO knowledge_employee_libraries(settings_id,knowledge_base_id) VALUES (?,?)",
                (setting, kb),
            )
            cases.append((setting, strategy, mode, top_k))
    command.upgrade(config, "0027")
    with sqlite3.connect(path) as db:
        assert "strategy" not in {
            row[1] for row in db.execute("PRAGMA table_info(knowledge_employee_settings)")
        }
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT count(*) FROM knowledge_employee_libraries").fetchone()[0] == 4
        for setting, strategy, mode, top_k in cases:
            assert db.execute(
                "SELECT revision,mode,top_k FROM knowledge_employee_settings WHERE id=?", (setting,)
            ).fetchone() == (7 if strategy == "auto" else 8, mode, top_k)
