import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

from app.common.errors import ConflictError
from app.resources.employees.access import assert_web_access, authorize_execution, configured_agent


def create_employee(client, **values):
    response = client.post("/api/agents", json={"name": "网页员工", "avatar_id": "admin", **values})
    assert response.status_code == 201, response.text
    return response.json()


def test_web_permission_defaults_off_and_round_trips_all_employee_views(api_client):
    employee = create_employee(api_client)
    assert employee["allow_web_access"] is False
    path = f"/api/agents/{employee['id']}"
    enabled = api_client.patch(
        path, json={"expected_revision": employee["revision"], "allow_web_access": True}
    ).json()
    assert enabled["allow_web_access"] is True
    assert enabled["revision"] == employee["revision"] + 1
    assert enabled["tool_grants"] == []
    for url in (path, path + "/usage", f"/api/public/agents/{employee['id']}"):
        response = api_client.get(url)
        assert response.status_code == 200, response.text
        assert response.json()["allow_web_access"] is True
    for url in ("/api/agents", "/api/public/agents"):
        assert api_client.get(url).json()["items"][0]["allow_web_access"] is True
    unchanged = api_client.patch(path, json={"expected_revision": enabled["revision"]}).json()
    assert unchanged["allow_web_access"] is True
    assert unchanged["revision"] == enabled["revision"]
    unchanged = api_client.patch(
        path, json={"expected_revision": enabled["revision"], "allow_web_access": True}
    ).json()
    assert unchanged["revision"] == enabled["revision"]
    stale = api_client.patch(
        path, json={"expected_revision": employee["revision"], "allow_web_access": False}
    )
    assert stale.status_code == 409
    assert api_client.get(path).json()["allow_web_access"] is True
    disabled = api_client.patch(
        path, json={"expected_revision": enabled["revision"], "allow_web_access": False}
    ).json()
    assert disabled["allow_web_access"] is False
    assert disabled["revision"] == enabled["revision"] + 1


@pytest.mark.parametrize("invalid", [None, 0, 1, "true", "false", [], {}])
def test_web_permission_requires_strict_boolean_for_create_and_patch(api_client, invalid):
    created = api_client.post(
        "/api/agents", json={"name": "无效", "avatar_id": "admin", "allow_web_access": invalid}
    )
    assert created.status_code == 422
    employee = create_employee(api_client, allow_web_access=True)
    path = f"/api/agents/{employee['id']}"
    patched = api_client.patch(
        path,
        json={"expected_revision": employee["revision"], "allow_web_access": invalid},
    )
    assert patched.status_code == 422
    assert api_client.get(path).json()["allow_web_access"] is True


def test_web_permission_rolls_back_with_other_invalid_employee_changes(api_client):
    employee = create_employee(api_client)
    path = f"/api/agents/{employee['id']}"
    response = api_client.patch(
        path,
        json={
            "expected_revision": employee["revision"],
            "allow_web_access": True,
            "model_connection_id": str(uuid4()),
        },
    )
    assert response.status_code == 404
    current = api_client.get(path).json()
    assert current["allow_web_access"] is False
    assert current["revision"] == employee["revision"]


def test_web_access_requires_frozen_and_live_permission_without_blocking_non_web_authorization(
    api_client,
):
    connection = api_client.post(
        "/api/model-connections", json={"name": "测试大脑", "api_key": "fixture-key"}
    ).json()
    employee = create_employee(
        api_client, model_connection_id=connection["id"], allow_web_access=True
    )
    snapshot = {
        "agent_id": employee["id"],
        "connection_id": connection["id"],
        "skills": [],
        "allow_web_access": True,
    }
    database = api_client.app.state.database
    with database.transaction() as db:
        assert configured_agent(db, employee["id"]).allow_web_access is True
        assert_web_access(db, snapshot)
        for captured in (False, None, 1, "true"):
            with pytest.raises(ConflictError) as error:
                assert_web_access(db, {**snapshot, "allow_web_access": captured})
            assert error.value.code == "web_access_revoked"
        with pytest.raises(ConflictError):
            assert_web_access(
                db, {key: value for key, value in snapshot.items() if key != "allow_web_access"}
            )
    changed = api_client.patch(
        f"/api/agents/{employee['id']}",
        json={"expected_revision": employee["revision"], "allow_web_access": False},
    )
    assert changed.status_code == 200
    with database.transaction() as db:
        assert configured_agent(db, employee["id"]).allow_web_access is False
        with pytest.raises(ConflictError) as error:
            assert_web_access(db, snapshot)
        assert error.value.code == "web_access_revoked"
        authorize_execution(db, snapshot, [])


def test_0030_migration_preserves_employees_and_defaults_off(app_config, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", app_config.database.url.render_as_string(hide_password=False)
    )
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0029")
    employee = str(uuid4())
    with sqlite3.connect(app_config.database.url.database) as db:
        db.execute(
            "INSERT INTO agents(id,name,avatar_id,revision,system_prompt) VALUES (?,?,?,7,?)",
            (employee, "历史员工", "admin", "保留原指令"),
        )
        before = db.execute("SELECT * FROM agents WHERE id=?", (employee,)).fetchone()
    command.upgrade(config, "0030")
    with sqlite3.connect(app_config.database.url.database) as db:
        after = db.execute("SELECT * FROM agents WHERE id=?", (employee,)).fetchone()
        assert after[:-1] == before
        assert after[-1] == 0
        db.execute(
            "INSERT INTO agents(id,name,avatar_id) VALUES (?, '新员工', 'admin')", (str(uuid4()),)
        )
        assert db.execute("SELECT allow_web_access FROM agents").fetchall() == [(0,), (0,)]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE agents SET allow_web_access=2 WHERE id=?", (employee,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE agents SET allow_web_access=NULL WHERE id=?", (employee,))
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    command.downgrade(config, "0029")
    with sqlite3.connect(app_config.database.url.database) as db:
        assert db.execute("SELECT * FROM agents WHERE id=?", (employee,)).fetchone() == before
    command.upgrade(config, "0030")
