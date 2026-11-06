"""Known conflicts remain actionable; unrelated database failures retain their identity."""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bootstrap import create_app
from app.employees.models import Agent
from app.model_connections.models import ModelConnection
from app.skills.models import Skill

INPUTS = {
    "agents": {"name": "original", "avatar_id": "admin", "code": "original-code"},
    "skills": {"name": "original"},
    "model-connections": {"name": "original", "api_key": "test-only-credential"},
}
REVISIONS = {
    "agents": {"expected_revision": 1},
    "model-connections": {"expected_config_revision": 1, "expected_credential_revision": 1},
}
FAILURES = {
    "not_null": "INSERT INTO error_probe VALUES (2, NULL, 1, 1)",
    "check": "INSERT INTO error_probe VALUES (2, 'different', 0, 1)",
    "foreign_key": "INSERT INTO error_probe VALUES (2, 'different', 1, 999)",
    "unrelated_unique": "INSERT INTO error_probe VALUES (2, 'original', 1, 1)",
}


@pytest.fixture
def probe(api_client):
    with api_client.app.state.database.engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE error_parent (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO error_parent VALUES (1)")
        connection.exec_driver_sql(
            "CREATE TABLE error_probe (id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE, "
            "revision INTEGER CHECK (revision > 0), "
            "parent_id INTEGER REFERENCES error_parent(id))"
        )
        connection.exec_driver_sql("INSERT INTO error_probe VALUES (1, 'original', 1, 1)")


@contextmanager
def fail_flush(model, statement):
    errors = []

    def inject(session, _context, _instances):
        if any(isinstance(row, model) for row in session.new | session.dirty | session.deleted):
            try:
                session.connection().exec_driver_sql(statement)
            except IntegrityError as error:
                errors.append(error)
                raise

    event.listen(Session, "before_flush", inject)
    try:
        yield errors
    finally:
        event.remove(Session, "before_flush", inject)


@pytest.mark.parametrize("failure", FAILURES)
@pytest.mark.parametrize(
    ("resource", "operation", "model"),
    [
        ("agents", "post", Agent),
        ("agents", "patch", Agent),
        ("skills", "delete", Skill),
        ("model-connections", "post", ModelConnection),
        ("model-connections", "patch", ModelConnection),
        ("model-connections", "delete", ModelConnection),
    ],
)
def test_unknown_integrity_failures_return_safe_500_and_roll_back(
    api_client, probe, resource, operation, model, failure
):
    base = f"/api/{resource}"
    original = api_client.post(base, json=INPUTS[resource]).json()
    before = api_client.get(base).json()
    url = base if operation == "post" else f"{base}/{original['id']}"
    if operation == "post":
        payload = {**INPUTS[resource], "name": "different"}
        if resource == "agents":
            payload["code"] = "different-code"
    elif operation == "patch":
        payload = {**REVISIONS[resource], "name": "different"}
    else:
        payload = None
    with fail_flush(model, FAILURES[failure]) as errors:
        response = api_client.request(operation, url, json=payload)
    assert len(errors) == 1
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "internal_error"
    assert response.headers["X-Request-ID"]
    for private in ("error_probe", "INSERT", "constraint", "test-only-credential"):
        assert private not in response.text
    assert api_client.get(base).json() == before
    assert api_client.get(f"{base}/{original['id']}").json() == original


def test_service_preserves_unknown_integrity_failure_and_rolls_back(api_client, probe):
    from app.employees.schemas import AgentCreate

    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    with fail_flush(Agent, FAILURES["not_null"]) as errors:
        with pytest.raises(IntegrityError) as caught:
            api_client.app.state.agents.create(AgentCreate(**INPUTS["agents"]), actor)
    assert len(errors) == 1 and caught.value is errors[0]
    assert api_client.get("/api/agents").json()["total"] == 0


@pytest.mark.parametrize("operation", ["post", "patch"])
@pytest.mark.parametrize(
    ("resource", "field", "code"),
    [
        ("agents", "code", "agent_code_conflict"),
        ("model-connections", "name", "model_connection_conflict"),
    ],
)
def test_known_unique_conflicts_keep_the_business_response(
    api_client, resource, field, code, operation
):
    base = f"/api/{resource}"
    original = api_client.post(base, json=INPUTS[resource]).json()
    second_input = {**INPUTS[resource], "name": "second"}
    if resource == "agents":
        second_input["code"] = "second-code"
    second = api_client.post(base, json=second_input).json()
    before = api_client.get(base).json()
    if operation == "post":
        result = api_client.post(
            base, json={**second_input, "name": "third", field: original[field]}
        )
    else:
        result = api_client.patch(
            f"{base}/{second['id']}",
            json={**REVISIONS[resource], field: original[field]},
        )
    assert result.status_code == 409 and result.json()["detail"]["code"] == code
    assert api_client.get(base).json() == before


def test_unexpected_integrity_failure_returns_500_without_database_details(
    api_client, migrated_config, probe
):
    with (
        TestClient(
            create_app(migrated_config),
            cookies=api_client.cookies,
            headers=api_client.headers,
            raise_server_exceptions=False,
        ) as client,
        fail_flush(Agent, FAILURES["not_null"]),
    ):
        response = client.post("/api/agents", json=INPUTS["agents"])
    assert response.status_code == 500
    for private in ("error_probe", "INSERT", "constraint", "test-only-credential"):
        assert private not in response.text
    assert api_client.get("/api/agents").json()["total"] == 0
