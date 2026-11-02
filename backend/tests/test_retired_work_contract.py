"""Retired inputs remain readable, never replay as ordinary work, and do not alter request keys."""

from copy import deepcopy
from uuid import uuid4

import pytest
from test_conversations import send, setup_agent

from app.agent_runtime.contracts import RuntimeFailure, validate_snapshot
from app.execution.admission import request_digest
from app.execution.contracts import Completion
from app.execution.models import Run


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


@pytest.mark.parametrize("marker", ["work", "ci", "retired_work"])
def test_retired_reply_is_readable_but_never_retryable(api_client, marker):
    _, _, conversation = setup_agent(api_client)
    row = send(api_client, conversation, "保留历史输入").json()
    publisher = api_client.app.state.conversation_commands.publisher
    publisher(Completion(row["id"], "保留历史正文", "failed", error="execution_failed"))
    with api_client.app.state.database.transaction() as db:
        run = db.get(Run, row["id"])
        run.config_snapshot = {**run.config_snapshot, marker: {"kind": "github_ci_diagnosis"}}
        run.error_code = "ci_evidence_invalid"
    historical = api_client.get(f"/api/runs/{row['id']}").json()
    assert historical["content"] == "保留历史正文"
    assert historical["can_retry"] is False
    assert "仅可查看" in historical["error"]["message"]
    assert "重试" not in historical["error"]["message"]
    assert "ci" not in historical and "work_kind" not in historical
    retried = api_client.post(
        f"/api/runs/{row['id']}/retry", json={"client_request_id": str(uuid4())}
    )
    assert retried.status_code == 409 and retried.json()["detail"]["code"] == "retry_not_allowed"
    assert send(api_client, conversation, "继续普通对话").status_code == 202


def test_ordinary_replay_preserves_pre_retirement_digest_and_retry_availability(api_client):
    _, _, conversation = setup_agent(api_client)
    key = str(uuid4())
    accepted = send(api_client, conversation, "原请求", key).json()
    expected = request_digest(
        {
            "conversation_id": conversation["id"],
            "retry_id": None,
            "content": "原请求",
            "work": None,
            "selected_skill_ids": [],
            "agent_id": None,
            "file_ids": [],
        }
    )
    with api_client.app.state.database.transaction() as db:
        assert db.get(Run, accepted["id"]).request_hash == expected
    replayed = send(api_client, conversation, "原请求", key)
    assert replayed.status_code == 200 and replayed.json()["id"] == accepted["id"]
    assert replayed.json()["can_retry"] is False
    api_client.app.state.conversation_commands.publisher(
        Completion(accepted["id"], None, "failed", error="execution_failed")
    )
    assert api_client.get(f"/api/runs/{accepted['id']}").json()["can_retry"] is True
    send(api_client, conversation, "新问题")
    assert api_client.get(f"/api/runs/{accepted['id']}").json()["can_retry"] is False


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
    accepted = send(api_client, conversation).json()
    row, messages = api_client.app.state.execution_store.load(accepted["id"])
    original = deepcopy(row.config_snapshot)
    assert validate_snapshot(original)["agent_id"] == row.agent_id
    row.config_snapshot[field] = value
    monkeypatch.setattr(
        api_client.app.state.model_connections,
        "resolve",
        lambda *args: pytest.fail("Invalid snapshot reached credential resolution"),
    )
    with pytest.raises(RuntimeFailure, match="checkpoint_unavailable"):
        api_client.app.state.conversation_commands.assembler.execution(row, messages)
