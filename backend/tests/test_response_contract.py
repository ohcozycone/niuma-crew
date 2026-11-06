"""Current wire protocol, atomic reads and durable reply ownership (no adapter)."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from run_helpers import complete_run, empty_conversation
from sqlalchemy import inspect, select

from app.bootstrap import create_app
from app.conversations import queries
from app.conversations.models import ConversationRun, Message
from app.execution.contracts import Completion


@pytest.fixture
def wire(api_client, migrated_config):
    with TestClient(
        create_app(migrated_config),
        headers={"Origin": "http://localhost:3000", "Content-Type": "application/json"},
    ) as client:
        client.cookies.update(api_client.cookies)
        yield client


def employee(client):
    connection = client.post(
        "/api/model-connections", json={"name": str(uuid4()), "api_key": "fixture"}
    ).json()
    return client.post(
        "/api/agents",
        json={"name": str(uuid4()), "avatar_id": "admin", "model_connection_id": connection["id"]},
    ).json()


def submit(client, conversation, agent, key=None, content="原问题"):
    return client.post(
        f"/api/conversations/{conversation}/messages",
        json={
            "client_request_id": key or str(uuid4()),
            "content": content,
            "agent_id": agent["id"],
        },
    )


def test_accept_replay_confirmation_history_and_sse_share_one_reply(wire):
    agent = employee(wire)
    conversation, key = empty_conversation(wire, agent["id"])["id"], str(uuid4())
    accepted = submit(wire, conversation, agent, key)
    assert accepted.status_code == 202
    value = accepted.json()
    response = value["response"]
    assert response["role"] == "assistant" and response["content_state"] == "empty"
    assert value["conversation"]["active_response_id"] == response["id"]
    assert response["reply_to_message_id"] == value["input_message"]["id"]
    assert "result" not in response and "current_model" not in response
    with wire.app.state.database.transaction() as db:
        assert len(list(db.scalars(select(Message)))) == 2
        assert "run_results" not in inspect(db.bind).get_table_names()
        binding = db.get(ConversationRun, response["id"])
        assert binding.run_id == response["id"] and binding.active
    complete_run(wire)(Completion(response["id"], "完整回复", "succeeded"))
    replay = submit(wire, conversation, agent, key)
    assert replay.status_code == 200
    replay = replay.json()
    assert replay["response"]["id"] == response["id"]
    assert replay["response"]["content_state"] == "complete"
    assert replay["conversation"]["version"] > value["conversation"]["version"]
    assert replay["conversation"]["active_response_id"] is None
    assert wire.get(f"/api/conversations/{conversation}/requests/{key}").json() == replay
    current = wire.get(f"/api/conversations/{conversation}/responses/{response['id']}").json()
    assert current == {"conversation": replay["conversation"], "response": replay["response"]}
    history = wire.get(f"/api/conversations/{conversation}/messages").json()
    assert history["items"][-1] == current["response"]
    events = wire.get(f"/api/conversations/{conversation}/responses/{response['id']}/events")
    assert "event: response.finished" in events.text
    event = json.loads(
        next(line[6:] for line in events.text.splitlines() if line.startswith("data: "))
    )
    assert event == current and wire.app.state.subscriptions == {}
    assert wire.get(f"/api/runs/{response['id']}").status_code == 404
    assert wire.post(f"/api/conversations/{conversation}/runs", json={}).status_code == 404


def test_retry_retains_input_and_failure_and_late_stop_targets_only_its_reply(wire):
    agent = employee(wire)
    conversation = empty_conversation(wire, agent["id"])["id"]
    first = submit(wire, conversation, agent).json()
    first_reply = first["response"]["id"]
    publisher = complete_run(wire)
    publisher(Completion(first_reply, "明确保留的片段", "failed", "output_limit_exceeded"))
    path = f"/api/conversations/{conversation}/responses/{first_reply}"
    key = str(uuid4())
    retry = wire.post(path + "/retry", json={"client_request_id": key})
    assert retry.status_code == 202
    retry = retry.json()
    assert retry["input_message"] == first["input_message"]
    assert retry["response"]["id"] != first_reply
    assert retry["response"]["retry_of_response_id"] == first_reply
    assert wire.post(path + "/stop", json={}).json()["response"]["status"] == "failed"
    active = wire.get(f"/api/conversations/{conversation}/snapshot").json()
    assert active["conversation"]["active_response_id"] == retry["response"]["id"]
    assert [item["role"] for item in active["messages"]["items"]] == [
        "user",
        "assistant",
        "assistant",
    ]
    assert active["messages"]["items"][1]["content"] == "明确保留的片段"
    assert (
        wire.post(path + "/retry", json={"client_request_id": key}).json()["response"]["id"]
        == retry["response"]["id"]
    )
    assert wire.post(path + "/retry", json={"client_request_id": str(uuid4())}).status_code == 409
    # Correct reply identity in the wrong conversation cannot grant access.
    other = empty_conversation(wire, agent["id"])["id"]
    assert (
        wire.post(f"/api/conversations/{other}/responses/{first_reply}/stop", json={}).status_code
        == 404
    )


def test_snapshot_remains_one_sqlite_snapshot_when_acceptance_commits_between_reads(
    wire, monkeypatch
):
    agent = employee(wire)
    conversation = empty_conversation(wire, agent["id"])["id"]
    entered, release = Event(), Event()
    original = queries.read_conversation
    paused = False

    def pause(db, row):
        nonlocal paused
        result = original(db, row)
        if not paused:
            paused = True
            entered.set()
            assert release.wait(4)
        return result

    monkeypatch.setattr(queries, "read_conversation", pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(wire.get, f"/api/conversations/{conversation}/snapshot")
        assert entered.wait(4)
        try:
            accepted = submit(wire, conversation, agent)
            assert accepted.status_code == 202
        finally:
            release.set()
        snapshot = reading.result(5).json()
    assert snapshot["conversation"]["active_response_id"] is None
    assert snapshot["messages"]["items"] == [] and snapshot["question_count"] == 0
    assert wire.get(f"/api/conversations/{conversation}/snapshot").json()["question_count"] == 1


def test_publication_authorization_uses_its_current_session_and_rolls_back_all_outputs(wire):
    agent = employee(wire)
    conversation = empty_conversation(wire, agent["id"])["id"]
    accepted = submit(wire, conversation, agent).json()
    id = accepted["response"]["id"]
    publisher = complete_run(wire)
    service = wire.app.state.runs
    original = service.authorize
    seen = []

    def check(row, active=(), db=None):
        assert db is not None and db.in_transaction()
        seen.append(db)
        return original(row, active, db=db)

    service.authorize = check
    publisher(Completion(id, "正式结果", "succeeded"))
    assert len(seen) == 1
    publisher(Completion(id, "迟到结果", "succeeded"))
    assert len(seen) == 1
    assert (
        wire.get(
            f"/api/conversations/{conversation}/responses/{accepted['response']['id']}"
        ).json()["response"]["content"]
        == "正式结果"
    )
