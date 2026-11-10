import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL


def test_employee_knowledge_and_tool_changes_save_atomically(api_client):
    library = api_client.post(
        "/api/knowledge-bases", json={"name": "组织资料", "client_request_id": str(uuid4())}
    ).json()
    agent = api_client.post("/api/agents", json={"name": "组织员工", "avatar_id": "admin"}).json()
    proposed = {"knowledge_base_ids": [library["id"]], "mode": "always", "top_k": 4}
    failed = api_client.patch(
        "/api/agents/" + agent["id"],
        json={
            "expected_revision": 1,
            "name": "不应保存",
            "knowledge": proposed,
            "tool_grants": [{"connection_id": str(uuid4()), "tools": [], "scope_policy": {}}],
        },
    )
    assert failed.status_code == 404, failed.text
    current = api_client.get("/api/agents/" + agent["id"]).json()
    assert (
        current["name"] == "组织员工"
        and current["knowledge"]["knowledge_base_ids"] == []
        and current["revision"] == 1
    )
    saved = api_client.patch(
        "/api/agents/" + agent["id"], json={"expected_revision": 1, "knowledge": proposed}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["knowledge"] == proposed
    assert saved.json()["resource_counts"]["knowledge_bases"] == 1
    assert (
        api_client.get("/api/agents").json()["items"][0]["resource_counts"]["knowledge_bases"] == 1
    )
    assert (
        api_client.get("/api/public/agents/" + agent["id"]).json()["resource_counts"][
            "knowledge_bases"
        ]
        == 1
    )
    assert (
        api_client.patch(
            "/api/agents/" + agent["id"], json={"expected_revision": 1, "knowledge": proposed}
        ).status_code
        == 409
    )
    duplicate = {**proposed, "knowledge_base_ids": [library["id"], library["id"]]}
    assert (
        api_client.patch(
            "/api/agents/" + agent["id"], json={"expected_revision": 2, "knowledge": duplicate}
        ).status_code
        == 422
    )
    assert api_client.get("/api/agents/" + agent["id"]).json()["revision"] == 2


def test_organization_migration_requires_explicit_choice_and_preserves_settings(
    tmp_path, monkeypatch
):
    import sqlite3

    path = tmp_path / "organization.db"
    monkeypatch.setenv("DATABASE_URL", str(URL.create("sqlite+pysqlite", database=str(path))))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0027")
    user, agent, library, setting = [str(uuid4()) for _ in range(4)]
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO users(id,username,role,password_hash) VALUES (?,'owner','admin','fixture-hash')",
            (user,),
        )
        db.execute("INSERT INTO agents(id,name,avatar_id) VALUES (?,'员工','admin')", (agent,))
        db.execute(
            "INSERT INTO knowledge_bases(id,owner_user_id,client_request_id,name,description) VALUES (?,?,?,'资料','')",
            (library, user, str(uuid4())),
        )
        db.execute(
            "INSERT INTO knowledge_employee_settings(id,user_id,agent_id,mode,top_k) VALUES (?,?,?,'always',9)",
            (setting, user, agent),
        )
        db.execute("INSERT INTO knowledge_employee_libraries VALUES (?,?)", (setting, library))
    with pytest.raises(RuntimeError, match="接纳清单"):
        command.upgrade(config, "head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0027"
        assert db.execute("SELECT count(*) FROM knowledge_employee_libraries").fetchone()[0] == 1
        assert "knowledge_mode" not in {r[1] for r in db.execute("PRAGMA table_info(agents)")}
    manifest = tmp_path / "组织资源接纳清单.json"
    data = {
        "schema_version": 1,
        "connections": [],
        "knowledge_bases": [library],
        "employee_tools": {},
        "employee_knowledge": {agent: str(uuid4())},
    }
    manifest.write_text(json.dumps(data))
    from argparse import Namespace

    config.cmd_opts = Namespace(x=["org_assets=" + str(manifest)])
    with pytest.raises(RuntimeError, match="配置选择无效"):
        command.upgrade(config, "head")
    data["employee_knowledge"][agent] = setting
    manifest.write_text(json.dumps(data))
    command.upgrade(config, "head")
    command.check(config)
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT knowledge_mode,knowledge_top_k FROM agents WHERE id=?", (agent,)
        ).fetchone() == ("always", 9)
        assert db.execute(
            "SELECT agent_id,knowledge_base_id FROM agent_knowledge_libraries"
        ).fetchall() == [(agent, library)]
        assert db.execute("SELECT created_by_user_id FROM knowledge_bases").fetchone() == (user,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert not {
            "personal_tool_bindings",
            "knowledge_employee_settings",
            "knowledge_employee_libraries",
        } & {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    with pytest.raises(RuntimeError, match="不能无损降级"):
        command.downgrade(config, "0027")
