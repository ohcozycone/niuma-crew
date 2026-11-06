"""Diagnostic ID lookup keeps old attempts precise and respects the history scope."""

from dataclasses import replace
from uuid import uuid4

from test_conversations import send, setup_agent

from app.auth.permissions import ROLE_PERMISSIONS


def test_lookup_matches_conversation_and_old_run_without_replacing_latest(api_client, monkeypatch):
    _, agent, conversation = setup_agent(api_client)
    first = send(api_client, conversation, "报销制度怎么查").json()["response"]["id"]
    stopped = api_client.post(
        f"/api/conversations/{conversation['id']}/responses/{first}/stop", json={}
    )
    assert stopped.status_code == 200
    second_response = send(api_client, conversation, "再问一次")
    assert second_response.status_code == 202, second_response.text
    second = second_response.json()["response"]["id"]
    _, other_agent, other_conversation = setup_agent(api_client)
    # An unrelated title containing a Run ID must not shadow exact diagnostic lookup.
    assert send(api_client, other_conversation, first).status_code == 202
    for value in [conversation["id"], first]:
        response = api_client.get("/api/conversations", params={"q": value})
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["total"] == 1
        row = page["items"][0]
        assert row["id"] == conversation["id"] and row["last_response_id"] == second
        assert row["matched_response_id"] == (first if value == first else None)
    assert api_client.get("/api/conversations", params={"q": "报销制度"}).json()["total"] == 1
    for value in ["%", "_", "000000000001", "1١١١١١١١١١١١"]:
        response = api_client.get("/api/conversations", params={"q": value})
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 0
    assert (
        api_client.get(
            "/api/conversations", params={"q": first, "agent_id": other_agent["id"]}
        ).json()["total"]
        == 0
    )
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    monkeypatch.setitem(ROLE_PERMISSIONS, "log-reader", {"conversations:read"})
    stranger = replace(actor, user_id=str(uuid4()), role="log-reader")
    queries = api_client.app.state.conversation_queries
    for value in [conversation["id"], first]:
        assert queries.list(stranger, q=value).total == 0
    owner = replace(actor, role="log-reader")
    assert queries.list(owner, q=first).items[0].matched_response_id == first
