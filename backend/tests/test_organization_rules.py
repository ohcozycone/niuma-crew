"""Shared rule persistence, authorization and optimistic updates using isolated SQLite."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.bootstrap import create_app

URL = "/api/organization-rules"


def test_rules_lifecycle_revision_and_restart(api_client, migrated_config):
    initial = api_client.get(URL).json()
    assert initial["instructions"] == "" and initial["revision"] == 0
    saved = api_client.put(URL, json={"instructions": "## 准则\n不要编造执行结果。", "revision": 0})
    assert saved.status_code == 200
    current = saved.json()
    assert current["revision"] == 1 and current["updated_at"] >= initial["updated_at"]
    assert (
        api_client.put(URL, json={"instructions": current["instructions"], "revision": 1}).json()
        == current
    )
    stale = api_client.put(URL, json={"instructions": "旧草稿", "revision": 0})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "rules_revision_conflict"
    assert api_client.get(URL).json() == current
    with TestClient(create_app(migrated_config)) as restarted:
        restarted.cookies.update(api_client.cookies)
        assert restarted.get(URL).json() == current
    cleared = api_client.put(URL, json={"instructions": " \n ", "revision": 1}).json()
    assert cleared["instructions"] == "" and cleared["revision"] == 2


def test_rules_permissions_and_origin(api_client, migrated_config):
    with TestClient(create_app(migrated_config)) as other:
        assert other.get(URL).status_code == 401
        assert (
            other.put(
                URL,
                json={"instructions": "", "revision": 0},
                headers={"Origin": "http://localhost:3000"},
            ).status_code
            == 401
        )
        assert (
            other.post(
                "/api/auth/guest", json={}, headers={"Origin": "http://localhost:3000"}
            ).status_code
            == 200
        )
        assert other.get(URL).status_code == 403
        assert (
            other.put(
                URL,
                json={"instructions": "", "revision": 0},
                headers={"Origin": "http://localhost:3000"},
            ).status_code
            == 403
        )
    assert (
        api_client.put(
            URL,
            json={"instructions": "变更", "revision": 0},
            headers={"Origin": "https://untrusted.example"},
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"instructions": ""},
        {"instructions": None, "revision": 0},
        {"instructions": 3, "revision": 0},
        {"instructions": "x" * 20001, "revision": 0},
        {"instructions": "", "revision": -1},
        {"instructions": "", "revision": True},
        {"instructions": "", "revision": "0"},
        {"instructions": "", "revision": 0, "id": 1},
    ],
)
def test_rules_reject_invalid_replacements(api_client, payload):
    assert api_client.put(URL, json=payload).status_code == 422
    assert api_client.get(URL).json()["revision"] == 0


def test_concurrent_rule_updates_only_one_wins(api_client):
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda content: api_client.put(URL, json={"instructions": content, "revision": 0}),
                ["规则甲", "规则乙"],
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 409]
    saved = next(response.json() for response in responses if response.status_code == 200)
    assert api_client.get(URL).json() == saved


def test_rules_database_constraints(api_client):
    database = api_client.app.state.database
    for sql in [
        "INSERT INTO organization_rules (id) VALUES (2)",
        "UPDATE organization_rules SET revision = -1",
        "UPDATE organization_rules SET instructions = :instructions",
    ]:
        with pytest.raises(IntegrityError):
            with database.transaction() as session:
                session.execute(text(sql), {"instructions": "x" * 20001})
