"""Reject unsupported inputs and malformed current execution snapshots."""

from copy import deepcopy
from uuid import uuid4

import pytest
from run_helpers import complete_run, read_reply
from test_conversations import send, setup_agent

from app.execution.contracts import Completion, RuntimeFailure, validate_snapshot
from app.execution.models import Run
from app.execution.service import request_digest


def test_retired_routes_are_absent_and_old_inputs_are_rejected(api_client):
    _, agent, conversation = setup_agent(api_client)
    paths = api_client.get("/openapi.json").json()["paths"]
    assert not any("ci-diagnosis" in path or "ci-feedback" in path for path in paths)
    for method, path in (
        ("GET", "/api/ci-diagnosis/capability"),
        ("POST", "/api/ci-diagnosis/skill"),
        ("GET", f"/api/conversations/{conversation['id']}/responses/{uuid4()}/ci-diagnosis"),
        ("POST", f"/api/conversations/{conversation['id']}/responses/{uuid4()}/ci-feedback"),
    ):
        assert api_client.request(method, path).status_code == 404
    for value in (None, {"kind": "github_ci_diagnosis", "run_url": "https://example.test/run"}):
        assert (
            api_client.post(
                f"/api/conversations/{conversation['id']}/messages",
                json={"client_request_id": str(uuid4()), "content": "旧输入", "work": value},
            ).status_code
            == 422
        )
    assert (
        api_client.patch(
            f"/api/agents/{agent['id']}",
            json={"expected_revision": agent["revision"], "ci_repository": None},
        ).status_code
        == 422
    )


def test_ordinary_replay_preserves_current_digest_and_retry_availability(api_client):
    _, _, conversation = setup_agent(api_client)
    key = str(uuid4())
    accepted = send(api_client, conversation, "原请求", key).json()["response"]
    expected = request_digest(
        {
            "conversation_id": conversation["id"],
            "retry_id": None,
            "content": "原请求",
            "selected_skill_ids": [],
            "agent_id": None,
            "file_ids": [],
        }
    )
    with api_client.app.state.database.transaction() as db:
        assert db.get(Run, accepted["id"]).request_hash == expected
    replayed = send(api_client, conversation, "原请求", key)
    assert replayed.status_code == 200 and replayed.json()["response"]["id"] == accepted["id"]
    assert replayed.json()["response"]["can_retry"] is False
    complete_run(api_client)(Completion(accepted["id"], None, "failed", error="execution_failed"))
    assert read_reply(api_client, accepted["id"])["can_retry"] is True
    send(api_client, conversation, "新问题")
    assert read_reply(api_client, accepted["id"])["can_retry"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("skills", None),
        ("selected_skill_ids", [1]),
        ("max_model_calls", True),
        ("run_timeout", float("inf")),
        ("connection_config_revision", 0),
    ],
)
def test_malformed_snapshot_stops_before_credentials_and_model(
    api_client, monkeypatch, field, value
):
    _, _, conversation = setup_agent(api_client)
    accepted = send(api_client, conversation).json()["response"]
    row, messages = api_client.app.state.run_worker.store.load(accepted["id"])
    original = deepcopy(row.config_snapshot)
    assert validate_snapshot(original)["agent_id"] == row.agent_id
    row.config_snapshot[field] = value
    monkeypatch.setattr(
        api_client.app.state.model_connections,
        "resolve",
        lambda *args: pytest.fail("Invalid snapshot reached credential resolution"),
    )
    with pytest.raises(RuntimeFailure, match="checkpoint_unavailable"):
        worker = api_client.app.state.run_worker
        task = worker.task_factory(row.id, worker._complete)
        task.row = row
        task._prepare()
