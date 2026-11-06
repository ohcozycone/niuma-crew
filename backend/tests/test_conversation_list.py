"""List filters describe the latest attempt within one authorized result set."""

from dataclasses import replace
from uuid import uuid4

import pytest
from run_helpers import complete_run, empty_conversation, reply_path
from sqlalchemy import event
from test_conversations import send, setup_agent

from app.conversations.models import ConversationRun
from app.conversations.queries import ConversationQueries
from app.execution.contracts import Completion


def test_latest_attempt_filters_pending_adoption_and_literal_search(api_client):
    _, agent, topic = setup_agent(api_client)
    first = send(api_client, topic, "预算 100%_核对").json()["response"]
    complete_run(api_client)(
        Completion(run_id=first["id"], status="failed", content=None, error="upstream_unavailable")
    )
    retry = api_client.post(
        reply_path(api_client, first["id"]) + "/retry",
        json={"client_request_id": str(uuid4())},
    ).json()["response"]
    api_client.app.state.runs.complete(
        Completion(run_id=retry["id"], status="succeeded", content="已核对")
    )
    empty_conversation(api_client, agent["id"])
    base = {"agent_id": agent["id"]}
    pending = api_client.get("/api/conversations", params={**base, "status": "processing"}).json()
    assert pending["total"] == 1  # 空话题不算处理中。
    assert pending["items"][0]["latest_response"] == {
        "id": retry["id"],
        "status": "succeeded",
        "acceptance": "pending",
    }
    api_client.app.state.conversation_acceptance.process(retry["id"])
    assert (
        api_client.get("/api/conversations", params={**base, "status": "attention"}).json()["total"]
        == 0
    )
    assert (
        api_client.get("/api/conversations", params={**base, "status": "replied"}).json()["total"]
        == 1
    )
    assert api_client.get("/api/conversations", params={**base, "q": "%_"}).json()["total"] == 1
    assert api_client.get("/api/conversations", params={**base, "q": "不存在"}).json()["total"] == 0
    assert (
        api_client.get("/api/conversations", params={**base, "status": "invented"}).status_code
        == 422
    )


def test_search_counts_page_scope_and_bounded_queries(api_client):
    _, agent, _ = setup_agent(api_client)
    database = api_client.app.state.database
    from app.conversations.models import Conversation

    for index in range(23):
        topic = empty_conversation(api_client, agent["id"])
        with database.transaction() as db:
            db.get(Conversation, topic["id"]).title = f"设计评审 {index}"
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    queries = ConversationQueries(database)
    statements = []

    def record(_, __, statement, *args):
        statements.append(statement)

    event.listen(database.engine, "before_cursor_execute", record)
    try:
        page = queries.list(actor, agent["id"], 20, 20, q="设计评审")
    finally:
        event.remove(database.engine, "before_cursor_execute", record)
    assert page.total == 23
    assert len(page.items) == 3
    assert len(statements) == 2  # 计数和当前页，不逐行读取回复或步骤。
    assert all("run_actions" not in statement for statement in statements)
    member = replace(actor, role="member")
    assert queries.list(member, agent["id"], q="设计评审").total == 23
    assert queries.list(replace(member, user_id=str(uuid4())), agent["id"], q="设计评审").total == 0


@pytest.mark.parametrize(
    "state,group", [("failed", "attention"), ("interrupted", "attention"), ("cancelled", "stopped")]
)
def test_terminal_status_groups_and_failed_adoption(api_client, state, group):
    _, agent, topic = setup_agent(api_client)
    reply = send(api_client, topic).json()["response"]
    complete_run(api_client)(
        Completion(
            run_id=reply["id"],
            status=state,
            content=None,
            error="upstream_unavailable" if state == "failed" else None,
        )
    )
    params = {"agent_id": agent["id"], "status": group}
    response = api_client.get("/api/conversations", params=params)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["latest_response"]["status"] == state
    with api_client.app.state.database.transaction() as db:
        db.get(ConversationRun, reply["id"]).acceptance_error = "写入失败"
    attention = api_client.get(
        "/api/conversations", params={**params, "status": "attention"}
    ).json()
    assert attention["items"][0]["latest_response"]["acceptance"] == "failed"
