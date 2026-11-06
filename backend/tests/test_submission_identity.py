"""Server-owned identities and first-send idempotency through the actual HTTP contract."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from test_response_contract import employee

from app.conversations.models import Conversation, ConversationRun, Message
from app.errors import ServiceUnavailableError
from app.execution.contracts import Completion
from app.execution.models import Run
from app.infrastructure.database.identifiers import MAX_ID, IdentifierSequence, allocate_id
from app.infrastructure.database.session import Database


def first_input(client, **changes):
    return {
        "agent_id": employee(client)["id"],
        "content": "第一次提问",
        "client_request_id": str(uuid4()),
        **changes,
    }


def test_first_submission_returns_server_conversation_and_shared_execution_key(api_client):
    data = first_input(api_client)
    accepted = api_client.post("/api/conversations", json=data)
    assert accepted.status_code == 202, accepted.text
    value = accepted.json()
    conversation, reply, question = (
        value[name]["id"] for name in ("conversation", "response", "input_message")
    )
    assert all(
        len(identifier) == 12 and identifier.isdecimal()
        for identifier in (conversation, reply, question)
    )
    assert len({conversation, reply, question}) == 3
    with api_client.app.state.database.transaction() as db:
        assert db.get(Run, reply).input_snapshot == [
            {"id": question, "role": "user", "content": data["content"]}
        ]
        assert db.get(Message, reply).role == "assistant"
        assert db.get(ConversationRun, reply).input_message_id == question
        assert db.execute(text("SELECT typeof(id) FROM runs")).scalar_one() == "integer"
    replay = api_client.post("/api/conversations", json=data)
    assert replay.status_code == 200 and replay.json()["conversation"]["id"] == conversation
    found = api_client.get(f"/api/conversations/requests/{data['client_request_id']}")
    assert found.status_code == 200 and found.json()["response"]["id"] == reply


def test_parallel_first_send_and_lost_receipt_create_only_one_conversation(api_client):
    data = first_input(api_client)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(lambda _: api_client.post("/api/conversations", json=data), range(4))
        )
    assert sorted(result.status_code for result in results) == [200, 200, 200, 202]
    assert len({result.json()["conversation"]["id"] for result in results}) == 1
    with api_client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Conversation)) == 1
        assert db.scalar(select(func.count()).select_from(Run)) == 1
        assert db.scalar(select(func.count()).select_from(Message)) == 2


def test_reused_creation_key_with_changed_input_rolls_back(api_client):
    data = first_input(api_client)
    assert api_client.post("/api/conversations", json=data).status_code == 202
    conflict = api_client.post("/api/conversations", json={**data, "content": "另一条问题"})
    assert (
        conflict.status_code == 409 and conflict.json()["detail"]["code"] == "idempotency_conflict"
    )
    with api_client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Conversation)) == 1
        assert db.scalar(select(func.count()).select_from(Message)) == 2


def test_identifier_sequence_is_unique_across_connections_and_survives_restart(
    api_client, migrated_config
):
    database = api_client.app.state.database

    def reserve(_):
        with database.transaction() as db:
            return allocate_id(db)

    with ThreadPoolExecutor(max_workers=4) as executor:
        identifiers = list(executor.map(reserve, range(20)))
    assert len(set(identifiers)) == 20
    reopened = Database(migrated_config.database)
    try:
        with reopened.transaction() as db:
            assert int(allocate_id(db)) > max(map(int, identifiers))
    finally:
        reopened.close()


def test_identifier_limit_refuses_overflow_without_wrapping(api_client):
    with api_client.app.state.database.transaction() as db:
        db.get(IdentifierSequence, 1).next_value = MAX_ID
    with api_client.app.state.database.transaction() as db:
        assert allocate_id(db) == str(MAX_ID)
    with pytest.raises(ServiceUnavailableError, match="标识号段不可用"):
        with api_client.app.state.database.transaction() as db:
            allocate_id(db)


def test_success_without_checkpoint_does_not_import_display_history(api_client):
    value = api_client.post("/api/conversations", json=first_input(api_client)).json()
    run_id = value["response"]["id"]
    api_client.app.state.runs.complete(Completion(run_id, "仅用于展示的历史答案", "succeeded"))
    api_client.app.state.conversation_acceptance.process(run_id)
    result = api_client.post(
        f"/api/conversations/{value['conversation']['id']}/messages",
        json={
            "content": "下一问",
            "client_request_id": str(uuid4()),
        },
    )
    assert result.status_code == 409 and result.json()["detail"]["code"] == "checkpoint_unavailable"
    with api_client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 2
        assert db.scalar(select(func.count()).select_from(Run)) == 1


def test_numeric_identity_preserves_saved_identity_immutability(api_client):
    value = api_client.post("/api/conversations", json=first_input(api_client)).json()
    with api_client.app.state.database.transaction() as db:
        for model, name in (
            (Conversation, "conversation"),
            (Message, "input_message"),
            (Run, "response"),
        ):
            row = db.get(model, value[name]["id"])
            with pytest.raises(ValueError, match="ID 不可修改"):
                row.id = "999999999999"
            assert row.id == value[name]["id"]
