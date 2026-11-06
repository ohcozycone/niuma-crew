"""Employee round totals use real completion/adoption and authorized visibility."""

from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from run_helpers import complete_run, empty_conversation, reply_path
from test_conversations import send, setup_agent

from app.auth.models import User
from app.auth.permissions import ROLE_PERMISSIONS
from app.bootstrap import create_app
from app.conversations.queries import ConversationQueries
from app.errors import PermissionDeniedError
from app.execution.contracts import Completion


def stats(client, agent_id):
    response = client.get("/api/conversations/stats", params={"agent_id": agent_id})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["completed_rounds"]


def test_counts_adopted_successes_and_one_round_after_retries(api_client):
    _, agent, conversation = setup_agent(api_client)
    assert stats(api_client, agent["id"]) == 0
    first = send(api_client, conversation).json()["response"]
    assert stats(api_client, agent["id"]) == 0
    api_client.app.state.runs.complete(
        Completion(run_id=first["id"], content="回答", status="succeeded")
    )
    assert stats(api_client, agent["id"]) == 0  # 成功执行尚未正式接纳。
    api_client.app.state.conversation_acceptance.process(first["id"])
    assert stats(api_client, agent["id"]) == 1

    retry_conversation = empty_conversation(api_client, agent["id"])
    failed = send(api_client, retry_conversation, "再问一个问题").json()["response"]
    complete_run(api_client)(
        Completion(run_id=failed["id"], content=None, status="failed", error="upstream_unavailable")
    )
    assert stats(api_client, agent["id"]) == 1
    retry = api_client.post(
        reply_path(api_client, failed["id"]) + "/retry",
        json={"client_request_id": str(uuid4())},
    )
    assert retry.status_code == 202, retry.text
    reply = retry.json()["response"]
    assert reply["reply_to_message_id"] == failed["reply_to_message_id"]
    complete_run(api_client)(Completion(run_id=reply["id"], content="重试成功", status="succeeded"))
    api_client.app.state.conversation_acceptance.process(reply["id"])
    assert stats(api_client, agent["id"]) == 2

    _, other, other_conversation = setup_agent(api_client)
    other_reply = send(api_client, other_conversation).json()["response"]
    complete_run(api_client)(
        Completion(run_id=other_reply["id"], content="其他员工回答", status="succeeded")
    )
    assert stats(api_client, other["id"]) == 1
    assert stats(api_client, agent["id"]) == 2


@pytest.mark.parametrize("status", ["failed", "cancelled", "interrupted"])
def test_incomplete_rounds_are_not_counted(api_client, status):
    _, agent, conversation = setup_agent(api_client)
    reply = send(api_client, conversation).json()["response"]
    complete_run(api_client)(Completion(run_id=reply["id"], content=None, status=status))
    assert stats(api_client, agent["id"]) == 0


def test_rejected_adoption_is_not_a_completed_round(api_client, monkeypatch):
    _, agent, conversation = setup_agent(api_client)
    reply = send(api_client, conversation).json()["response"]
    api_client.app.state.runs.complete(
        Completion(run_id=reply["id"], content="已执行但未接纳", status="succeeded")
    )

    def denied(*args, **kwargs):
        raise PermissionDeniedError("permission_denied", "当前身份无权接纳。")

    monkeypatch.setattr(api_client.app.state.conversation_acceptance, "authorize", denied)
    api_client.app.state.conversation_acceptance.process(reply["id"])
    assert stats(api_client, agent["id"]) == 0


def test_member_visibility_and_guest_permissions(api_client, migrated_config, monkeypatch):
    _, agent, conversation = setup_agent(api_client)
    reply = send(api_client, conversation).json()["response"]
    complete_run(api_client)(Completion(run_id=reply["id"], content="回答", status="succeeded"))
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    database = api_client.app.state.database
    with database.transaction() as db:
        member = User(username="other-member", password_hash=None, role="member")
        db.add(member)
        db.flush()
        member_id = member.id
    queries = ConversationQueries(database)
    assert queries.stats(replace(actor, role="member"), agent["id"]).completed_rounds == 1
    other_actor = replace(actor, user_id=member_id, username="other-member", role="member")
    assert queries.stats(other_actor, agent["id"]).completed_rounds == 0
    assert api_client.get(f"/api/conversations/stats?agent_id={uuid4()}").status_code == 404
    assert api_client.get("/api/conversations/stats?agent_id=invalid").status_code == 422
    with TestClient(
        create_app(migrated_config), headers={"Origin": "http://localhost:3000"}
    ) as guest:
        assert guest.get(f"/api/conversations/stats?agent_id={agent['id']}").status_code == 401
        guest.post("/api/auth/guest", json={})
        assert guest.get(f"/api/conversations/stats?agent_id={agent['id']}").status_code == 403
    monkeypatch.setitem(ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] - {"runs:read"})
    assert api_client.get(f"/api/conversations/stats?agent_id={agent['id']}").status_code == 403
