"""Target configuration API: revisions, atomic assembly edits and bounded projections."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest
from configuration_helpers import patch_current
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.employees.models import AgentSkill
from app.infrastructure.database.session import Database
from app.skills.models import Skill


def create_skill(client, **values):
    response = client.post(
        "/api/skills", json={"name": "文档摘要", "instructions": "核对原文", **values}
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_agent(client, **values):
    response = client.post(
        "/api/agents", json={"name": f"行政管家-{uuid4()}", "avatar_id": "admin", **values}
    )
    assert response.status_code == 201, response.text
    return response.json()


def assignment(skill, **values):
    return {"skill_id": skill["id"], **values}


def test_agent_name_conflicts_normalize_whitespace_and_preserve_aggregate(api_client):
    existing = create_agent(api_client, name=" \t老赵\u3000", is_active=False)
    assert existing["name"] == "老赵"
    duplicate = api_client.post("/api/agents", json={"name": "老赵", "avatar_id": "admin"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "agent_name_conflict",
        "message": "员工名称已存在，请换个名字。",
    }
    assert api_client.get("/api/agents").json()["total"] == 1

    skill = create_skill(api_client)
    other = create_agent(api_client, name="小李", skill_assignments=[assignment(skill)])
    url = f"/api/agents/{other['id']}"
    conflict = patch_current(
        api_client,
        url,
        json={"name": " 老赵 ", "system_prompt": "不能保存", "skill_assignments": []},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "agent_name_conflict"
    assert api_client.get(url).json() == other
    unchanged = patch_current(api_client, url, json={"name": " 小李 "})
    assert unchanged.status_code == 200 and unchanged.json() == other
    renamed = patch_current(api_client, url, json={"name": "小王"})
    assert renamed.status_code == 200 and renamed.json()["revision"] == 2
    assert renamed.json()["id"] == other["id"]
    assert renamed.json()["skill_assignments"] == other["skill_assignments"]
    create_agent(api_client, name="小李")


def test_agent_names_compare_exactly_after_trimming(api_client):
    create_agent(api_client, name="Alice")
    create_agent(api_client, name="alice")
    duplicate = api_client.post("/api/agents", json={"name": " Alice ", "avatar_id": "admin"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "agent_name_conflict"


@pytest.mark.parametrize("operation", ["create", "rename"])
def test_concurrent_agent_names_only_one_wins(api_client, operation):
    agents = [create_agent(api_client, name=name) for name in ("甲", "乙")]

    def save(agent):
        if operation == "create":
            return api_client.post("/api/agents", json={"name": "老赵", "avatar_id": "admin"})
        return api_client.patch(
            f"/api/agents/{agent['id']}", json={"expected_revision": 1, "name": "老赵"}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, agents))
    assert sorted(r.status_code for r in results) == [200 if operation == "rename" else 201, 409]
    loser = next(r for r in results if r.status_code == 409)
    assert loser.json()["detail"]["code"] == "agent_name_conflict"
    assert (
        len([a for a in api_client.get("/api/agents").json()["items"] if a["name"] == "老赵"]) == 1
    )


def test_create_and_restart_preserve_configuration(api_client, migrated_config):
    skill = create_skill(api_client)
    agent = create_agent(
        api_client,
        code=" OS-001 ",
        role_label="ROLE",
        system_prompt="第一步\n  第二步",
        is_favorite=True,
        example_tasks=["示例"],
        deliverables=["摘要"],
        skill_assignments=[assignment(skill)],
    )
    assert agent["code"] == "OS-001" and agent["revision"] == 1
    relation = agent["skill_assignments"][0]
    assert relation["parameters"] == {} and relation["enabled"] and relation["ready"]
    assert relation["revision"] == 1 and agent["resource_counts"]["skills"] == 1
    with TestClient(create_app(migrated_config), cookies=api_client.cookies) as reopened:
        assert reopened.get(f"/api/agents/{agent['id'].upper()}").json() == agent


def test_revisions_reject_stale_and_concurrent_edits(api_client):
    agent = create_agent(api_client)
    url = f"/api/agents/{agent['id']}"
    assert api_client.patch(url, json={"name": "缺修订"}).status_code == 422
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda name: api_client.patch(url, json={"expected_revision": 1, "name": name}),
                ["甲", "乙"],
            )
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    current = api_client.get(url).json()
    assert current["revision"] == 2
    assert (
        api_client.patch(url, json={"expected_revision": 1, "system_prompt": "旧草稿"}).status_code
        == 409
    )
    assert api_client.get(url).json() == current


def test_partial_edit_omits_preserve_explicit_empty_clears(api_client):
    skill = create_skill(api_client)
    agent = create_agent(
        api_client,
        code="OS-001",
        system_prompt="职责",
        example_tasks=["示例"],
        skill_assignments=[assignment(skill)],
    )
    url = f"/api/agents/{agent['id']}"
    changed = patch_current(api_client, url, json={"name": "新名"}).json()
    assert changed["skill_assignments"] == agent["skill_assignments"]
    assert changed["system_prompt"] == "职责" and changed["revision"] == 2
    cleared = patch_current(
        api_client, url, json={"code": None, "skill_assignments": [], "example_tasks": []}
    ).json()
    assert (
        cleared["skill_assignments"] == []
        and cleared["code"] is None
        and cleared["example_tasks"] == []
    )
    assert cleared["system_prompt"] == "职责"


def test_parameter_validation_relationship_revision_and_atomic_rollback(api_client):
    schema = {
        "type": "object",
        "properties": {"tone": {"type": "string", "enum": ["formal", "brief"]}},
        "required": ["tone"],
        "additionalProperties": False,
    }
    skill = create_skill(api_client, configuration_schema=schema)
    agent = create_agent(
        api_client, skill_assignments=[assignment(skill, parameters={"tone": "brief"})]
    )
    url = f"/api/agents/{agent['id']}"
    for parameters in [
        {},
        {"tone": 1},
        {"tone": "other"},
        {"tone": "brief", "secret": "must-not-echo"},
    ]:
        result = patch_current(
            api_client,
            url,
            json={
                "name": "不能部分保存",
                "skill_assignments": [assignment(skill, parameters=parameters)],
            },
        )
        assert result.status_code == 422 and "must-not-echo" not in result.text
        assert api_client.get(url).json() == agent
    changed = patch_current(
        api_client,
        url,
        json={
            "skill_assignments": [assignment(skill, enabled=False, parameters={"tone": "formal"})]
        },
    ).json()
    relation = changed["skill_assignments"][0]
    assert changed["revision"] == 2 and relation["revision"] == 2 and not relation["ready"]
    assert relation["updated_at"] >= relation.get("created_at", agent["created_at"])
    # Shared schema edits cannot invalidate enabled assignments; disable/migrate first.
    patch_current(
        api_client,
        url,
        json={"skill_assignments": [assignment(skill, parameters={"tone": "brief"})]},
    )
    new_schema = {**schema, "properties": {"tone": {"type": "integer"}}}
    conflict = api_client.patch(
        f"/api/skills/{skill['id']}",
        json={"expected_revision": 1, "configuration_schema": new_schema},
    )
    assert conflict.status_code == 422
    assert api_client.get(f"/api/skills/{skill['id']}").json()["revision"] == 1


def test_empty_schema_draft_readiness_and_invalid_schema(api_client):
    skill = create_skill(api_client, instructions="")
    bad = api_client.post(
        "/api/agents",
        json={
            "name": "甲",
            "avatar_id": "admin",
            "skill_assignments": [assignment(skill, parameters={"unexpected": 1})],
        },
    )
    assert bad.status_code == 422 and api_client.get("/api/agents").json()["total"] == 0
    agent = create_agent(api_client, skill_assignments=[assignment(skill)])
    assert agent["skill_assignments"][0]["readiness_reason"] == "技能正文为空"
    for schema in [
        {"type": "object"},
        {"type": "array"},
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {"x": {"$ref": "https://example.invalid/schema"}},
        },
    ]:
        assert (
            api_client.post(
                "/api/skills", json={"name": "错误规范", "configuration_schema": schema}
            ).status_code
            == 422
        )


def test_assignment_keeps_identity_and_prevents_remove_readd_aba(api_client):
    first, second = create_skill(api_client), create_skill(api_client, name="改写")
    agent = create_agent(api_client, skill_assignments=[assignment(first)])
    url = f"/api/agents/{agent['id']}"
    database = api_client.app.state.database
    with database.transaction() as db:
        created = db.get(AgentSkill, (agent["id"], first["id"])).created_at
    changed = patch_current(
        api_client, url, json={"skill_assignments": [assignment(first), assignment(second)]}
    ).json()
    assert (
        next(a for a in changed["skill_assignments"] if a["skill_id"] == first["id"])["revision"]
        == 1
    )
    with database.transaction() as db:
        assert db.get(AgentSkill, (agent["id"], first["id"])).created_at == created
    patch_current(api_client, url, json={"skill_assignments": []})
    readded = patch_current(api_client, url, json={"skill_assignments": [assignment(first)]}).json()
    assert readded["skill_assignments"][0]["revision"] > 1
    assert (
        api_client.patch(
            url,
            json={
                "expected_revision": readded["revision"],
                "skill_assignments": [assignment(first), assignment(first)],
            },
        ).status_code
        == 422
    )


def test_missing_skill_and_duplicate_code_roll_back_every_field(api_client):
    skill = create_skill(api_client)
    create_agent(api_client, code="OS-001")
    agent = create_agent(api_client, code="OS-002", skill_assignments=[assignment(skill)])
    url = f"/api/agents/{agent['id']}"
    for changes, status in [
        ({"code": "OS-001", "skill_assignments": []}, 409),
        ({"name": "不应保存", "skill_assignments": [{"skill_id": str(uuid4())}]}, 404),
    ]:
        response = patch_current(api_client, url, json=changes)
        assert response.status_code == status
        if "code" in changes:
            assert response.json()["detail"]["code"] == "agent_code_conflict"
        assert api_client.get(url).json() == agent


def test_shared_skill_delete_protected_and_agent_delete_cascades(api_client):
    skill = create_skill(api_client)
    agents = [create_agent(api_client, skill_assignments=[assignment(skill)]) for _ in range(2)]
    url = f"/api/skills/{skill['id']}"
    for agent in agents:
        assert api_client.delete(url).status_code == 409
        assert api_client.delete(f"/api/agents/{agent['id']}").status_code == 204
    assert api_client.delete(url).status_code == 204


def test_skill_revisions_and_summary_projections(api_client):
    skill = create_skill(api_client, instructions="第一步\n  第二步")
    url = f"/api/skills/{skill['id']}"
    changed = api_client.patch(url, json={"expected_revision": 1, "is_active": False}).json()
    assert changed["revision"] == 2 and not changed["is_active"]
    assert (
        api_client.patch(url, json={"expected_revision": 1, "instructions": "旧稿"}).status_code
        == 409
    )
    create_agent(api_client, skill_assignments=[assignment(skill)])
    summary = api_client.get("/api/skills").json()["items"][0]
    assert summary["assignment_count"] == 1
    assert (
        not {"instructions", "configuration_schema", "input_description", "example"}
        & summary.keys()
    )
    agent = api_client.get("/api/agents").json()["items"][0]
    assert (
        not {"system_prompt", "skill_assignments", "example_tasks", "deliverables", "ci_repository"}
        & agent.keys()
    )
    assert agent["skill_summaries"][0]["name"] == skill["name"]


def test_list_filters_current_page_and_literal_search(api_client):
    skill = create_skill(api_client, name="100% 摘要")
    first = create_agent(
        api_client,
        name="100% 管家",
        category="行政",
        is_favorite=True,
        skill_assignments=[assignment(skill)],
    )
    second = create_agent(api_client, name="普通", category="行政", is_active=False)
    create_agent(api_client, name="其他", category="其他")
    listing = api_client.get("/api/agents").json()
    assert listing["total"] == 3
    page = api_client.get("/api/agents?offset=1&limit=1").json()
    assert page["total"] == 3 and page["items"][0]["id"] == listing["items"][1]["id"]
    for query in [{"q": "%"}, {"skill_id": skill["id"]}, {"is_favorite": True}, {"q": "摘要"}]:
        assert [e["id"] for e in api_client.get("/api/agents", params=query).json()["items"]] == [
            first["id"]
        ]
    assert (
        api_client.get("/api/agents?category=行政&is_active=false").json()["items"][0]["id"]
        == second["id"]
    )
    assert api_client.get("/api/skills", params={"q": "' OR 1=1 --"}).json()["total"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": " ", "avatar_id": "admin"},
        {"name": "甲", "avatar_id": ""},
        {"name": "甲", "avatar_id": "admin", "is_active": "false"},
        {"name": "甲", "avatar_id": "admin", "skill_ids": []},
        {"name": "甲", "avatar_id": "admin", "model_id": "legacy"},
    ],
)
def test_invalid_or_removed_create_fields_rejected(api_client, payload):
    assert api_client.post("/api/agents", json=payload).status_code == 422
    assert api_client.get("/api/agents").json()["total"] == 0


@pytest.mark.parametrize(
    "field", ["name", "system_prompt", "is_active", "skill_assignments", "example_tasks"]
)
def test_null_patch_rejected_without_changes(api_client, field):
    agent = create_agent(api_client)
    url = f"/api/agents/{agent['id']}"
    assert api_client.patch(url, json={"expected_revision": 1, field: None}).status_code == 422
    assert api_client.get(url).json() == agent


def test_removed_assignment_writes_and_readonly_fields_rejected(api_client):
    agent, skill = create_agent(api_client), create_skill(api_client)
    url = f"/api/agents/{agent['id']}"
    assert api_client.put(url + "/skills", json={"skill_ids": []}).status_code == 404
    assert api_client.put(url + "/skills/" + skill["id"]).status_code == 404
    assert (
        api_client.patch(
            url, json={"expected_revision": 1, "resource_counts": {"skills": 99}}
        ).status_code
        == 422
    )
    schema = api_client.get("/openapi.json").json()["components"]["schemas"]
    assert schema["AgentPatch"]["required"] == ["expected_revision"]
    assert "default" not in schema["AgentPatch"]["properties"]["name"]


@pytest.mark.parametrize("resource", ["agents", "skills"])
def test_resource_and_query_validation(api_client, resource):
    missing = f"/api/{resource}/{uuid4()}"
    assert api_client.get(missing).status_code == 404
    assert api_client.patch(missing, json={"expected_revision": 1}).status_code == 404
    assert api_client.delete(missing).status_code == 404
    assert api_client.get(f"/api/{resource}/not-a-uuid").status_code == 422
    for params in [{"offset": -1}, {"limit": 0}, {"limit": 101}]:
        assert api_client.get(f"/api/{resource}", params=params).status_code == 422


def test_database_lock_is_retryable_and_does_not_claim_success(migrated_config, api_client):
    config = replace(
        migrated_config, database=replace(migrated_config.database, busy_timeout_ms=20)
    )
    writer = Database(config.database)
    try:
        with TestClient(
            create_app(config), cookies=api_client.cookies, headers=api_client.headers
        ) as client:
            with writer.transaction() as db:
                db.add(Skill(name="占用写锁"))
                db.flush()
                result = client.post("/api/skills", json={"name": "尚未保存"})
                assert result.status_code == 503 and result.headers["Retry-After"] == "1"
                assert "INSERT" not in result.text
            assert client.get("/api/skills").json()["total"] == 1
    finally:
        writer.close()


def test_shell_aggregate_is_independent_of_page_and_safe_for_guest(api_client, migrated_config):
    create_agent(api_client, is_favorite=True)
    create_agent(api_client)
    create_skill(api_client)
    expected = {"agents": 2, "skills": 1, "favorites": 1}
    assert api_client.get("/api/configuration-summary").json() == expected
    with TestClient(create_app(migrated_config), headers=api_client.headers) as guest:
        assert guest.get("/api/public/configuration-summary").status_code == 401
        guest.post("/api/auth/guest", json={})
        assert guest.get("/api/configuration-summary").status_code == 403
        assert guest.get("/api/public/configuration-summary").json() == expected


def test_directory_queries_are_bounded_and_do_not_load_method_bodies(api_client):
    from sqlalchemy import event

    from app.employees.models import Agent
    from app.employees.service import AgentService

    database = api_client.app.state.database
    with database.transaction() as db:
        db.add_all(
            Agent(name=f"员工 {i}", avatar_id="admin", system_prompt="不应列表加载" * 100)
            for i in range(500)
        )
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    event.listen(database.engine, "before_cursor_execute", record)
    try:
        page = AgentService(database).list(actor=actor, offset=20, limit=20)
        assert page.total == 500 and len(page.items) == 20
        assert len(statements) == 3
        assert not any(
            "agents.system_prompt" in sql or "skills.instructions" in sql for sql in statements
        )
    finally:
        event.remove(database.engine, "before_cursor_execute", record)
